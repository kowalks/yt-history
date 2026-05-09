"""YouTube History Tracker module for scraping metadata.

This module initializes the database, tracks channels, and fetches
historical representations of YouTube videos over time.
"""

import sqlite3
from typing import Optional

import yt_dlp

DB_FILE = "history.db"


def init_db() -> None:
  """Initializes the SQLite database with necessary tables.

  Creates channels, videos, and video_snapshots tables if they do not exist.
  """
  connection = sqlite3.connect(DB_FILE)
  cursor = connection.cursor()
  cursor.executescript("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        handle TEXT UNIQUE,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY,
        channel_handle TEXT,
        published_date TEXT,
        first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS video_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        title TEXT,
        description TEXT,
        thumbnail_url TEXT,
        status TEXT,
        FOREIGN KEY(video_id) REFERENCES videos(id)
    );
    """)
  connection.commit()
  connection.close()


def add_channel(handle: str) -> None:
  """Adds a new YouTube channel to track.

  Args:
      handle: The YouTube handle (e.g., '@PrimoRico').
  """
  connection = sqlite3.connect(DB_FILE)
  cursor = connection.cursor()
  try:
    cursor.execute("INSERT INTO channels (handle) VALUES (?)", (handle,))
    connection.commit()
    print(f"Added channel: {handle}")
  except sqlite3.IntegrityError:
    print(f"Channel {handle} already exists.")
  connection.close()


def scrape_channel(handle: str, limit: Optional[int] = None) -> None:
  """Scrapes video metadata for the given channel handle.

  Fetches video titles, descriptions, thumbnails, and status to
  check if there is a divergence from the tracked history.

  Args:
      handle: The YouTube handle to scrape.
      limit: An optional restriction on how many recent videos to scrape.
  """
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

    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute(
      "UPDATE channels SET name = ? WHERE handle = ?", (channel_name, handle)
    )
    connection.commit()

    for entry in entries:
      if not entry:
        continue
      video_id = entry.get("id")
      video_title = entry.get("title")
      video_desc = entry.get("description", "")

      thumbnails = entry.get("thumbnails", [])
      if thumbnails:
        video_thumb = thumbnails[-1].get("url", "")
      else:
        video_thumb = entry.get("thumbnail", "")

      upload_date = entry.get("upload_date", "")
      status = "PUBLIC"

      try:
        cursor.execute(
          "INSERT OR IGNORE INTO videos (id, channel_handle, published_date) VALUES (?, ?, ?)",
          (video_id, handle, upload_date),
        )

        cursor.execute(
          """SELECT title, description, thumbnail_url, status
                       FROM video_snapshots
                       WHERE video_id = ?
                       ORDER BY retrieved_at DESC LIMIT 1""",
          (video_id,),
        )
        latest = cursor.fetchone()

        changed = False
        if not latest:
          changed = True
        else:
          if (
            latest[0] != video_title
            or latest[1] != video_desc
            or latest[2] != video_thumb
            or latest[3] != status
          ):
            changed = True

        if changed:
          print(f"New snapshot saved for video: {video_id} - '{video_title}'")
          cursor.execute(
            """INSERT INTO video_snapshots (video_id, title, description, thumbnail_url, status)
                           VALUES (?, ?, ?, ?, ?)""",
            (video_id, video_title, video_desc, video_thumb, status),
          )
        connection.commit()
      except sqlite3.DatabaseError as db_error:
        print(f"Database error for video {video_id}: {db_error}")

    connection.close()


if __name__ == "__main__":
  init_db()
  test_handle = "@PrimoRico"
  add_channel(test_handle)
  scrape_channel(test_handle)
