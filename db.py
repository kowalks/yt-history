import os
import sqlite3
import uuid
from typing import Optional

import pandas as pd

DB_FILE = os.path.join(os.path.dirname(__file__), "history.db")


def normalize_handle(handle: str) -> str:
  """Ensures handle always starts with '@'."""
  return f"@{handle.lstrip('@')}"


def get_connection() -> sqlite3.Connection:
  """Creates and returns a connection to the SQLite database."""
  return sqlite3.connect(DB_FILE)


def init_db() -> None:
  """Initializes the database schema."""
  print(f"🗄️ Initializing database at {DB_FILE}...")
  connection = get_connection()
  cursor = connection.cursor()
  cursor.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS channels (
        uuid TEXT PRIMARY KEY,
        name TEXT,
        handle TEXT UNIQUE,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS videos (
        uuid TEXT PRIMARY KEY,
        video_id TEXT,
        channel_uuid TEXT,
        title TEXT,
        description TEXT,
        thumbnail_url TEXT,
        status TEXT,
        duration_sec INTEGER,
        published_date TEXT,
        is_change BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(channel_uuid) REFERENCES channels(uuid)
    );
    CREATE TABLE IF NOT EXISTS scrapes (
        id TEXT PRIMARY KEY,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        status TEXT DEFAULT 'RUNNING',
        total_videos INTEGER DEFAULT 0,
        new_records INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS scrape_channels (
        scrape_id TEXT,
        channel_uuid TEXT,
        status TEXT,
        video_count INTEGER,
        FOREIGN KEY(scrape_id) REFERENCES scrapes(id),
        FOREIGN KEY(channel_uuid) REFERENCES channels(uuid)
    );
    CREATE TABLE IF NOT EXISTS scrape_videos (
        scrape_id TEXT,
        video_uuid TEXT,
        FOREIGN KEY(scrape_id) REFERENCES scrapes(id),
        FOREIGN KEY(video_uuid) REFERENCES videos(uuid)
    );
    CREATE INDEX IF NOT EXISTS idx_scrape_videos_scrape
      ON scrape_videos(scrape_id);
    CREATE INDEX IF NOT EXISTS idx_scrape_channels_scrape
      ON scrape_channels(scrape_id);
    CREATE INDEX IF NOT EXISTS idx_videos_id
      ON videos(video_id);
  """)
  connection.commit()
  connection.close()
  print("✅ Database initialized successfully.")


def reset_db() -> None:
  """Drops all tables and re-initializes from scratch."""
  print("⚠️ Purging all data by dropping tables...")
  connection = get_connection()
  cursor = connection.cursor()
  cursor.executescript("""
    PRAGMA foreign_keys = OFF;
    DROP TABLE IF EXISTS scrape_videos;
    DROP TABLE IF EXISTS scrape_channels;
    DROP TABLE IF EXISTS scrapes;
    DROP TABLE IF EXISTS videos;
    DROP TABLE IF EXISTS channels;
    PRAGMA foreign_keys = ON;
  """)
  connection.commit()
  connection.close()
  init_db()
  print("♻️ Database reset completed.")


def add_channel(handle: str, name: Optional[str] = None) -> None:
  """Adds a new channel handle or restores a deleted one."""
  handle = normalize_handle(handle)
  connection = get_connection()
  cursor = connection.cursor()
  try:
    cursor.execute(
      "INSERT INTO channels (handle, uuid, name) VALUES (?, ?, ?)",
      (handle, str(uuid.uuid4()), name),
    )
    connection.commit()
  except sqlite3.IntegrityError:
    # If exists, ensure it is not marked as deleted
    if name:
      cursor.execute(
        "UPDATE channels SET deleted_at = NULL, name = ? WHERE handle = ?",
        (name, handle),
      )
    else:
      cursor.execute(
        "UPDATE channels SET deleted_at = NULL WHERE handle = ?", (handle,)
      )
    connection.commit()
  connection.close()


def update_channel_name(handle: str, name: str) -> None:
  """Updates the display name for a channel."""
  handle = normalize_handle(handle)
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
  cursor.execute("SELECT count(DISTINCT video_id) FROM videos")
  videos = cursor.fetchone()[0]
  cursor.execute("SELECT count(*) FROM videos")
  records = cursor.fetchone()[0]
  connection.close()
  return {"channels": channels, "videos": videos, "records": records}


def get_channels_df(include_deleted: bool = False) -> pd.DataFrame:
  """Returns a DataFrame of tracked channels with video counts."""
  connection = get_connection()
  query = """
    SELECT
        c.name,
        c.handle,
        c.added_at,
        COUNT(v.uuid) as video_count
    FROM channels c
    LEFT JOIN videos v ON v.channel_uuid = c.uuid
  """
  if not include_deleted:
    query += " WHERE c.deleted_at IS NULL"
  query += " GROUP BY c.uuid"

  df = pd.read_sql_query(query, connection)
  connection.close()
  return df


def remove_channel(handle: str) -> None:
  """Marks a channel as deleted."""
  handle = normalize_handle(handle)
  connection = get_connection()
  cursor = connection.cursor()
  cursor.execute(
    "UPDATE channels SET deleted_at = CURRENT_TIMESTAMP WHERE handle = ?",
    (handle,),
  )
  connection.commit()
  connection.close()


def get_video_records_df() -> pd.DataFrame:
  """Returns a formatted DataFrame mapping records history."""
  connection = get_connection()
  df = pd.read_sql_query(
    """
    SELECT v.thumbnail_url, 'https://youtube.com/watch?v=' || v.video_id AS
           video_url, c.name AS channel_name, c.handle AS channel_handle,
           v.title, v.duration_sec, v.uuid as record_id, v.status,
           v.created_at AS recorded_at
    FROM videos v
    JOIN channels c ON v.channel_uuid = c.uuid
    ORDER BY v.created_at DESC
    """,
    connection,
  )
  connection.close()
  return df


def get_scrapes_df() -> pd.DataFrame:
  """Returns a detailed log of every channel-scrape event."""
  connection = get_connection()
  df = pd.read_sql_query(
    """
    SELECT 
        sc.scrape_id,
        c.name as channel_name,
        sc.video_count,
        sc.status as channel_status,
        s.started_at
    FROM scrape_channels sc
    JOIN scrapes s ON sc.scrape_id = s.id
    JOIN channels c ON sc.channel_uuid = c.uuid
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
    SELECT v.thumbnail_url, 'https://youtube.com/watch?v=' || v.video_id AS
           video_url, c.name AS channel_name, c.handle AS channel_handle,
           v.title, v.duration_sec, v.status, v.uuid as record_id
    FROM scrape_videos sv
    JOIN videos v ON sv.video_uuid = v.uuid
    JOIN channels c ON v.channel_uuid = c.uuid
    WHERE sv.scrape_id = ?
    """,
    connection,
    params=(scrape_id,),
  )
  connection.close()
  return df


def start_scrape_session(scrape_id: str) -> None:
  """Registers a new multi-channel scrape session."""
  print(f"🚀 Starting scrape session: {scrape_id}")
  connection = get_connection()
  cursor = connection.cursor()
  cursor.execute(
    "INSERT INTO scrapes (id) VALUES (?)",
    (scrape_id,),
  )
  connection.commit()
  connection.close()


def log_channel_scrape_result(
  scrape_id: str, handle: str, status: str, video_count: int
) -> None:
  """Logs the outcome of a specific channel's scrape within a session."""
  print(f"  ∟ {handle}: {status} ({video_count} videos)")
  connection = get_connection()
  cursor = connection.cursor()
  try:
    cursor.execute("SELECT uuid FROM channels WHERE handle = ?", (handle,))
    row = cursor.fetchone()
    channel_uuid = row[0] if row else None

    cursor.execute(
      """INSERT INTO scrape_channels (scrape_id, channel_uuid, status, 
         video_count)
         VALUES (?, ?, ?, ?)""",
      (scrape_id, channel_uuid, status, video_count),
    )
    connection.commit()
  except sqlite3.DatabaseError as e:
    print(f"Error logging channel result: {e}")
  finally:
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
  """Processes a video version using the flattened append-only model."""
  connection = get_connection()
  cursor = connection.cursor()
  status = "PUBLIC"

  try:
    # Lookup channel UUID
    cursor.execute("SELECT uuid FROM channels WHERE handle = ?", (handle,))
    row = cursor.fetchone()
    channel_uuid = row[0] if row else None

    # 1. Check if EXACT metadata version already exists for this video_id
    cursor.execute(
      """SELECT uuid
         FROM videos
         WHERE video_id = ? AND title = ? AND description = ?
           AND thumbnail_url = ? AND status = ? AND duration_sec = ?""",
      (video_id, title, description, thumbnail, status, duration),
    )
    existing = cursor.fetchone()

    if existing:
      final_uuid = existing[0]
    else:
      # 2. It's a new version or first time seeing this video.
      # Check if we have ANY previous version to determine 'is_change'
      cursor.execute(
        "SELECT count(*) FROM videos WHERE video_id = ?", (video_id,)
      )
      count = cursor.fetchone()[0]
      is_change = 1 if count > 0 else 0
      final_uuid = record_uuid

      if is_change:
        print(f"    ⚠️ Change detected for video: {video_id} ({title[:30]}...)")

      cursor.execute(
        """INSERT INTO videos
           (uuid, video_id, channel_uuid, title, description, thumbnail_url,
            status, duration_sec, published_date, is_change)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
          final_uuid,
          video_id,
          channel_uuid,
          title,
          description,
          thumbnail,
          status,
          duration,
          upload_date,
          is_change,
        ),
      )

    # 3. Link this scrape session to the correct version UUID
    cursor.execute(
      "INSERT INTO scrape_videos (scrape_id, video_uuid) VALUES (?, ?)",
      (scrape_id, final_uuid),
    )
    connection.commit()
  except sqlite3.DatabaseError as db_error:
    print(f"Database error for video {video_id}: {db_error}")
  finally:
    connection.close()


def get_metadata_changes_df() -> pd.DataFrame:
  """Finds videos with changed metadata using the is_change flag."""
  connection = get_connection()
  # Simplified query using the new is_change column
  query = """
    SELECT
        v.*,
        c.handle as channel_handle,
        c.name as channel_name,
        prev.title as prev_title,
        prev.description as prev_description,
        prev.status as prev_status,
        v.uuid as record_id
    FROM videos v
    JOIN channels c ON v.channel_uuid = c.uuid
    LEFT JOIN (
        SELECT video_id, title, description, status, created_at,
               ROW_NUMBER() OVER (
                 PARTITION BY video_id ORDER BY created_at DESC
               ) as rn
        FROM videos
    ) prev ON prev.video_id = v.video_id AND prev.rn = 2
    WHERE v.is_change = 1
    ORDER BY v.created_at DESC
  """
  df = pd.read_sql_query(query, connection)
  connection.close()
  return df


def finalize_scrape(scrape_id: str, status: str = "SUCCESS") -> None:
  """Updates a scrape event with completion status and metadata."""
  connection = get_connection()
  cursor = connection.cursor()

  # Calculate totals
  cursor.execute(
    "SELECT count(*), sum(v.is_change) "
    "FROM scrape_videos sv "
    "JOIN videos v ON sv.video_uuid = v.uuid "
    "WHERE sv.scrape_id = ?",
    (scrape_id,),
  )
  total, changes = cursor.fetchone()

  cursor.execute(
    """UPDATE scrapes
       SET ended_at = CURRENT_TIMESTAMP,
           status = ?,
           total_videos = ?,
           new_records = ?
       WHERE id = ?""",
    (status, total or 0, changes or 0, scrape_id),
  )
  connection.commit()
  connection.close()
  print(f"🏁 Scrape session {scrape_id} finalized: {status}")
  print(f"   📊 Total: {total or 0} videos | Changes detected: {changes or 0}")
