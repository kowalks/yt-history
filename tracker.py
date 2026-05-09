"""Coordinator for YouTube History Tracker. 
Maps scraper data to database logic and manages background sessions.
"""

import uuid
from typing import List, Optional

import db
from engine import scraper, worker


def get_channel_name(handle: str) -> Optional[str]:
    """Retrieves the display name for a channel handle. Returns None if not found."""
    try:
        info = scraper.fetch_channel_info(handle, playlist_limit=0)
        return (
            info.get("uploader") or 
            info.get("playlist_uploader") or 
            info.get("channel")
        )
    except Exception:
        return None


def scrape_channel(handle: str, limit: Optional[int] = None, scrape_uuid: Optional[str] = None) -> None:
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
            db.finalize_scrape(scrape_uuid, status="SUCCESS")

    except Exception as e:
        db.log_channel_scrape_result(scrape_uuid, handle, f"FAILED: {str(e)}", 0)
        if is_standalone:
            db.finalize_scrape(scrape_uuid, status=f"FAILED: {str(e)}")
        raise e


def _run_batch(handles: List[str], scrape_uuid: str):
    """Internal batch processor for background worker."""
    try:
        for handle in handles:
            try:
                scrape_channel(handle, scrape_uuid=scrape_uuid)
            except Exception as e:
                print(f"Batch error for {handle}: {e}")
        db.finalize_scrape(scrape_uuid, status="SUCCESS")
    except Exception as e:
        db.finalize_scrape(scrape_uuid, status=f"CRITICAL: {str(e)}")


def start_background_scrape(handles: List[str]) -> str:
    """Triggers a multi-channel scrape session in a background thread."""
    scrape_uuid = str(uuid.uuid4())
    db.start_scrape_session(scrape_uuid)
    worker.start_task(target=_run_batch, args=(handles, scrape_uuid))
    return scrape_uuid
