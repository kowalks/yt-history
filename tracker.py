"""Coordinator for YouTube History Tracker.
Maps scraper data to database logic and manages background sessions.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import db
from engine import fingerprinter, scraper, worker


def get_channel_name(handle: str) -> Optional[str]:
  """Retrieves the display name for a channel handle. Returns None if not found."""
  try:
    info = scraper.fetch_channel_info(handle, playlist_limit=0)
    return (
      info.get("uploader")
      or info.get("playlist_uploader")
      or info.get("channel")
    )
  except Exception:
    return None


def scrape_channel(
  handle: str, limit: Optional[int] = None, scrape_uuid: Optional[str] = None
) -> None:
  """Core logic to scrape a channel and persist to DB."""
  is_standalone = False
  if not scrape_uuid:
    scrape_uuid = str(uuid.uuid4())
    db.start_scrape_session(scrape_uuid)
    is_standalone = True

  try:
    info = scraper.fetch_channel_info(handle, playlist_limit=limit)

    # Update channel name if we found a better one
    display_name = info.get("uploader") or info.get("channel")
    if display_name:
      db.update_channel_name(handle, display_name)

    entries = info.get("entries", [])
    for entry in entries:
      if not entry:
        continue

      video_id = entry.get("id")
      thumbnail_url = entry.get("thumbnail")

      # Fallback for flat extraction missing thumbnails
      if not thumbnail_url and video_id:
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

      db.process_scraped_video(
        scrape_id=scrape_uuid,
        handle=handle,
        video_id=video_id,
        title=entry.get("title"),
        description=entry.get("description"),
        thumbnail=thumbnail_url,
        upload_date=entry.get("upload_date"),
        duration=entry.get("duration"),
        record_uuid=str(uuid.uuid4()),
      )

    db.log_channel_scrape_result(scrape_uuid, handle, "SUCCESS", len(entries))
    if is_standalone:
      audit_session_thumbnails(scrape_uuid)
      db.finalize_scrape(scrape_uuid, status="SUCCESS")

  except Exception as e:
    db.log_channel_scrape_result(scrape_uuid, handle, f"FAILED: {str(e)}", 0)
    if is_standalone:
      db.finalize_scrape(scrape_uuid, status=f"FAILED: {str(e)}")
    raise e


def audit_session_thumbnails(scrape_uuid: str):
  """Performs a deep visual audit of all thumbnails in a scrape session."""
  print(f"🔍 Starting Deep Visual Audit for session {scrape_uuid}...")
  df = db.get_scrape_videos_with_visuals(scrape_uuid)
  if df.empty:
    return

  def _process_one(row):
    video_uuid = row["video_uuid"]
    video_id = row["video_id"]
    thumb_url = row["thumbnail_url"]
    old_hash = row["thumbnail_hash"]

    # 1. Get current visual fingerprint
    etag, phash, content = fingerprinter.get_visual_fingerprint(thumb_url)
    if not phash:
      return

    # 2. Compare and Update/Archive
    if phash != old_hash:
      # It's a new visual version!
      print(f"    📸 Visual drift detected for {video_id}")
      new_uuid = str(uuid.uuid4())
      fingerprinter.archive_thumbnail(video_id, phash, content)
      db.promote_video_to_new_version(
        scrape_uuid, video_uuid, new_uuid, phash, etag
      )
    else:
      # Same visual, just update the hash/etag if they were missing
      if not old_hash:
        db.update_video_visuals(video_uuid, phash, etag)

  # Use parallel workers for high-speed audit
  with ThreadPoolExecutor(max_workers=20) as executor:
    list(executor.map(_process_one, df.to_dict("records")))

  print(f"✅ Visual audit complete for {len(df)} videos.")


def _run_batch(handles: list[str], scrape_uuid: str):
  """Internal batch processor for background worker."""
  try:
    for handle in handles:
      try:
        scrape_channel(handle, scrape_uuid=scrape_uuid)
      except Exception as e:
        print(f"Batch error for {handle}: {e}")

    # Run the deep visual audit on the whole batch
    audit_session_thumbnails(scrape_uuid)
    db.finalize_scrape(scrape_uuid, status="SUCCESS")
  except Exception as e:
    db.finalize_scrape(scrape_uuid, status=f"CRITICAL: {str(e)}")


def start_background_scrape(handles: list[str]) -> str:
  """Triggers a multi-channel scrape session in a background thread."""
  scrape_uuid = str(uuid.uuid4())
  db.start_scrape_session(scrape_uuid)
  worker.start_task(target=_run_batch, args=(handles, scrape_uuid))
  return scrape_uuid
