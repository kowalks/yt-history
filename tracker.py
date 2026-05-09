"""YouTube History Tracker module for scraping metadata."""

import uuid
from typing import Optional

import yt_dlp

import db


def scrape_channel(handle: str, limit: Optional[int] = None) -> None:
  """Scrapes video metadata for the given channel handle utilizing the DB API."""
  url = f"https://www.youtube.com/{handle}/videos"

  ydl_opts = {
    "extract_flat": "in_playlist",
    "skip_download": True,
    "quiet": True,
    "no_warnings": True,
  }

  if limit is not None:
    ydl_opts["playlistend"] = limit

  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    limit_str = f"limit {limit}" if limit else "all videos"
    print(
      f"Fetching metadata for {handle}/videos ({limit_str}). This may take a while..."
    )

    try:
      info = ydl.extract_info(url, download=False)
    except Exception as e:
      print(f"Unexpected error fetching channel: {e}")
      return

    entries = info.get("entries", [])
    channel_name = (
      info.get("uploader")
      or info.get("playlist_uploader")
      or info.get("channel")
      or handle
    )

    db.update_channel_name(handle, channel_name)

    scrape_id = str(uuid.uuid4())
    db.insert_scrape_event(scrape_id, handle)

    for entry in entries:
      if not entry:
        continue
      video_id = entry.get("id")
      video_title = entry.get("title")
      video_desc = entry.get("description", "")

      thumbnails = entry.get("thumbnails", [])
      video_thumb = (
        thumbnails[-1].get("url", "")
        if thumbnails
        else entry.get("thumbnail", "")
      )

      upload_date = entry.get("upload_date", "")
      video_duration = entry.get("duration")

      new_record_uuid = str(uuid.uuid4())
      db.process_scraped_video(
        scrape_id,
        handle,
        video_id,
        video_title,
        video_desc,
        video_thumb,
        upload_date,
        video_duration,
        new_record_uuid,
      )


if __name__ == "__main__":
  db.init_db()
  test_handle = "@PrimoRico"
  db.add_channel(test_handle)
  scrape_channel(test_handle)
