"""Streamlit dashboard for YouTube History Tracker.

This module processes sqlite data and launches the dashboard application.
"""

import sqlite3

import pandas as pd
import streamlit as st

DB_FILE = "history.db"

st.set_page_config(page_title="YouTube History Tracker", layout="wide")
st.title("📹 YouTube History Tracker")

st.sidebar.header("Navigation")
menu = st.sidebar.radio(
  "Go to", ["Dashboard", "Channels", "Snapshots", "Scraper Controls"]
)


def get_db_connection() -> sqlite3.Connection:
  """Creates and returns a connection to the SQLite history database.

  Returns:
      A valid connection object pointing to DB_FILE.
  """
  return sqlite3.connect(DB_FILE)


if menu == "Dashboard":
  st.header("Overview")
  st.write("Welcome to the YouTube History Tracker Prototype.")
  connection = get_db_connection()
  cursor = connection.cursor()

  cursor.execute("SELECT count(*) FROM channels")
  channels_count = cursor.fetchone()[0]

  cursor.execute("SELECT count(*) FROM videos")
  videos_count = cursor.fetchone()[0]

  cursor.execute("SELECT count(*) FROM video_snapshots")
  snapshots_count = cursor.fetchone()[0]

  col1, col2, col3 = st.columns(3)
  col1.metric("Channels Watched", channels_count)
  col2.metric("Videos Tracked", videos_count)
  col3.metric("Snapshots Recorded", snapshots_count)

  connection.close()

elif menu == "Channels":
  st.header("Channels")
  connection = get_db_connection()
  dataframe = pd.read_sql_query("SELECT * FROM channels", connection)
  st.dataframe(dataframe)
  connection.close()

elif menu == "Snapshots":
  st.header("Video Snapshots (History Log)")
  connection = get_db_connection()
  dataframe = pd.read_sql_query(
    """
        SELECT vs.thumbnail_url, 'https://youtube.com/watch?v=' || vs.video_id AS video_url, v.channel_handle, vs.title, vs.status, vs.retrieved_at
        FROM video_snapshots vs
        JOIN videos v ON v.id = vs.video_id
        ORDER BY vs.retrieved_at DESC
    """,
    connection,
  )

  st.dataframe(
    dataframe,
    column_config={
      "thumbnail_url": st.column_config.ImageColumn("Thumbnail"),
      "video_url": st.column_config.LinkColumn(
        "Video Link", display_text=r"https://youtube\.com/watch\?v=(.*)"
      ),
      "channel_handle": "Channel",
      "title": "Title",
      "status": "Status",
      "retrieved_at": "Retrieved At",
    },
    hide_index=True,
    width="stretch",
  )
  connection.close()
