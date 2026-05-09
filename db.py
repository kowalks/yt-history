"""Database Access API for YouTube History Tracker."""

import sqlite3
from typing import Optional

import pandas as pd

DB_FILE = "history.db"


def get_connection() -> sqlite3.Connection:
  """Creates and returns a connection to the SQLite database."""
  return sqlite3.connect(DB_FILE)


def init_db() -> None:
  """Initializes the database schema."""
  connection = get_connection()
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
    CREATE TABLE IF NOT EXISTS video_records (
        record_id TEXT PRIMARY KEY,
        video_id TEXT,
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
        record_id TEXT,
        FOREIGN KEY(scrape_id) REFERENCES scrapes(id),
        FOREIGN KEY(record_id) REFERENCES video_records(record_id)
    );
  """)
  connection.commit()
  connection.close()


def add_channel(handle: str) -> None:
  """Adds a new channel handle to track."""
  connection = get_connection()
  cursor = connection.cursor()
  try:
    cursor.execute("INSERT INTO channels (handle) VALUES (?)", (handle,))
    connection.commit()
  except sqlite3.IntegrityError:
    pass
  connection.close()


def update_channel_name(handle: str, name: str) -> None:
  """Updates the display name for a channel."""
  connection = get_connection()
  cursor = connection.cursor()
  cursor.execute(
    "UPDATE channels SET name = ? WHERE handle = ?", (name, handle)
  )
  connection.commit()
  connection.close()


def get_stats() -> dict[str, int]:
  """Retrieves total counts for channels, videos, and records."""
  connection = get_connection()
  cursor = connection.cursor()
  cursor.execute("SELECT count(*) FROM channels")
  channels = cursor.fetchone()[0]
  cursor.execute("SELECT count(*) FROM videos")
  videos = cursor.fetchone()[0]
  cursor.execute("SELECT count(*) FROM video_records")
  records = cursor.fetchone()[0]
  connection.close()
  return {"channels": channels, "videos": videos, "records": records}


def get_channels_df() -> pd.DataFrame:
  """Returns a DataFrame of all tracked channels."""
  connection = get_connection()
  df = pd.read_sql_query("SELECT * FROM channels", connection)
  connection.close()
  return df


def get_video_records_df() -> pd.DataFrame:
  """Returns a formatted DataFrame mapping records history."""
  connection = get_connection()
  df = pd.read_sql_query(
    """
    SELECT vr.thumbnail_url, 'https://youtube.com/watch?v=' || vr.video_id AS video_url,
           v.channel_handle, vr.title, v.duration_sec, vr.record_id, vr.status, vr.created_at AS recorded_at
    FROM video_records vr
    JOIN videos v ON v.id = vr.video_id
    ORDER BY vr.created_at DESC
    """,
    connection,
  )
  connection.close()
  return df


def get_scrapes_df() -> pd.DataFrame:
  """Returns a DataFrame of scrape audit events."""
  connection = get_connection()
  df = pd.read_sql_query(
    """
    SELECT s.id AS scrape_id, s.channel_handle, s.started_at, count(sv.record_id) as records_touched
    FROM scrapes s
    LEFT JOIN scrape_videos sv ON sv.scrape_id = s.id
    GROUP BY s.id
    ORDER BY s.started_at DESC
    """,
    connection,
  )
  connection.close()
  return df


def get_scrape_videos_df(scrape_id: str) -> pd.DataFrame:
  """Retrieve all video records tied to an explicit scrape execution."""
  connection = get_connection()
  df = pd.read_sql_query(
    """
    SELECT vr.thumbnail_url, 'https://youtube.com/watch?v=' || vr.video_id AS video_url,
           v.channel_handle, vr.title, v.duration_sec, vr.status
    FROM scrape_videos sv
    JOIN video_records vr ON sv.record_id = vr.record_id
    JOIN videos v ON vr.video_id = v.id
    WHERE sv.scrape_id = ?
    """,
    connection,
    params=(scrape_id,),
  )
  connection.close()
  return df


def insert_scrape_event(scrape_id: str, handle: str) -> None:
  """Registers a new scrape session trigger."""
  connection = get_connection()
  cursor = connection.cursor()
  cursor.execute(
    "INSERT INTO scrapes (id, channel_handle) VALUES (?, ?)",
    (scrape_id, handle),
  )
  connection.commit()
  connection.close()


def process_scraped_video(
  scrape_id: str,
  handle: str,
  video_id: str,
  title: str,
  description: str,
  thumbnail: str,
  upload_date: str,
  duration: Optional[int],
  record_uuid: str,
) -> None:
  """Processes a newly scraped video checking for equality."""
  connection = get_connection()
  cursor = connection.cursor()
  status = "PUBLIC"

  try:
    cursor.execute(
      """INSERT INTO videos
         (id, channel_handle, published_date, duration_sec)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(id) DO NOTHING""",
      (video_id, handle, upload_date, duration),
    )

    cursor.execute(
      """SELECT record_id
         FROM video_records
         WHERE video_id = ? AND title = ? AND description = ? AND thumbnail_url = ? AND status = ?
         LIMIT 1""",
      (video_id, title, description, thumbnail, status),
    )
    existing_record = cursor.fetchone()

    if existing_record:
      final_record_id = existing_record[0]
    else:
      final_record_id = record_uuid
      cursor.execute(
        """INSERT INTO video_records (record_id, video_id, title, description, thumbnail_url, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (final_record_id, video_id, title, description, thumbnail, status),
      )

    cursor.execute(
      "INSERT INTO scrape_videos (scrape_id, record_id) VALUES (?, ?)",
      (scrape_id, final_record_id),
    )
    connection.commit()
  except sqlite3.DatabaseError as db_error:
    print(f"Database error for video {video_id}: {db_error}")
  finally:
    connection.close()
