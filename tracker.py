"""YouTube History Tracker module for scraping metadata."""

import sqlite3
import uuid
from typing import Optional

import yt_dlp

DB_FILE = "history.db"


def init_db() -> None:
  """Initializes the SQLite database with necessary tables."""
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
        duration_sec INTEGER,
        first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS video_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        version_num INTEGER,
        title TEXT,
        description TEXT,
        thumbnail_url TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(video_id) REFERENCES videos(id)
    );

    CREATE TABLE IF NOT EXISTS scrapes (
        id TEXT PRIMARY KEY,
        channel_handle TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS scrape_videos (
        scrape_id TEXT,
        video_id TEXT,
        version_num INTEGER,
        FOREIGN KEY(scrape_id) REFERENCES scrapes(id),
        FOREIGN KEY(video_id) REFERENCES videos(id)
    );
    """)
  connection.commit()
  connection.close()


def add_channel(handle: str) -> None:
  """Adds a new YouTube channel to track."""
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
  """Scrapes video metadata for the given channel handle."""
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

    scrape_id = str(uuid.uuid4())
    cursor.execute(
      "INSERT INTO scrapes (id, channel_handle) VALUES (?, ?)",
      (scrape_id, handle),
    )
    connection.commit()

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
      status = "PUBLIC"

      try:
        cursor.execute(
          """INSERT INTO videos
             (id, channel_handle, published_date, duration_sec)
             VALUES (?, ?, ?, ?)
             ON CONFLICT(id) DO NOTHING""",
          (
            video_id,
            handle,
            upload_date,
            video_duration,
          ),
        )

        cursor.execute(
          """SELECT version_num
             FROM video_versions
             WHERE video_id = ? AND title = ? AND description = ? AND thumbnail_url = ? AND status = ?
             LIMIT 1""",
          (video_id, video_title, video_desc, video_thumb, status),
        )
        existing_version = cursor.fetchone()

        if existing_version:
          version_num = existing_version[0]
        else:
          cursor.execute(
            "SELECT MAX(version_num) FROM video_versions WHERE video_id = ?",
            (video_id,),
          )
          max_v = cursor.fetchone()[0]
          version_num = (max_v or 0) + 1

          print(
            f"New version ({version_num}) saved for video: {video_id} - '{video_title}'"
          )
          cursor.execute(
            """INSERT INTO video_versions (video_id, version_num, title, description, thumbnail_url, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
              video_id,
              version_num,
              video_title,
              video_desc,
              video_thumb,
              status,
            ),
          )

        cursor.execute(
          "INSERT INTO scrape_videos (scrape_id, video_id, version_num) VALUES (?, ?, ?)",
          (scrape_id, video_id, version_num),
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
