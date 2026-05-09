"""Streamlit dashboard for YouTube History Tracker.

This module processes sqlite data and launches the dashboard application.
"""

import sqlite3

import pandas as pd
import streamlit as st

import tracker

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
        SELECT vs.thumbnail_url, 'https://youtube.com/watch?v=' || vs.video_id AS video_url,
               v.channel_handle, vs.title, v.duration_sec, v.view_count, v.like_count, vs.status, vs.retrieved_at
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
      "duration_sec": st.column_config.NumberColumn(
        "Duration (s)", format="%d"
      ),
      "view_count": st.column_config.NumberColumn("Views", format="%d"),
      "like_count": st.column_config.NumberColumn("Likes", format="%d"),
      "status": "Status",
      "retrieved_at": "Retrieved At",
    },
    hide_index=True,
    width="stretch",
    height=800,
  )
  connection.close()

elif menu == "Scraper Controls":
  st.header("Scraper Controls")
  st.write(
    "Trigger the backend scraping algorithms directly from this interface."
  )

  st.subheader("1. Add New Channel", divider="gray")
  new_handle = st.text_input("YouTube Handle (e.g., @mkbhd)")
  if st.button("Add Channel"):
    if new_handle:
      tracker.add_channel(new_handle)
      st.success(f"Added {new_handle} to the database. You can now scrape it!")
    else:
      st.error("Please enter a valid YouTube handle.")

  st.subheader("2. Trigger Scraping Action", divider="gray")
  connection = get_db_connection()
  channels_df = pd.read_sql_query(
    "SELECT handle, name FROM channels", connection
  )
  connection.close()

  handles_list = channels_df["handle"].tolist()

  if not handles_list:
    st.warning("No channels active. Add a channel above first.")
  else:
    scrape_options = ["All Channels"] + handles_list
    selected_option = st.selectbox("Select Target", scrape_options)

    limit_val = st.number_input(
      "Maximum videos to scrape (0 for all historical archive)",
      min_value=0,
      value=10,
      step=10,
    )

    if st.button("Run Scraper", type="primary"):
      final_limit = None if limit_val == 0 else limit_val

      if selected_option == "All Channels":
        with st.spinner(
          "Scraping all registered channels... This may take a while depending on limits."
        ):
          for h in handles_list:
            tracker.scrape_channel(h, limit=final_limit)
        st.success("Successfully completed scraping all channels!")
      else:
        with st.spinner(f"Scraping '{selected_option}'..."):
          tracker.scrape_channel(selected_option, limit=final_limit)
        st.success(f"Successfully scraped {selected_option}!")
