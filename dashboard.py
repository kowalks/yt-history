"""Streamlit dashboard for YouTube History Tracker.

This module renders the frontend relying on the internal db API.
"""

import streamlit as st

import db
import tracker

st.set_page_config(page_title="YouTube History Tracker", layout="wide")
st.title("📹 YouTube History Tracker")

st.sidebar.header("Navigation")
menu = st.sidebar.radio(
  "Go to", ["Dashboard", "Channels & Controls", "History Log"]
)

if menu == "Dashboard":
  st.header("Overview")
  st.write("Welcome to the YouTube History Tracker Prototype.")

  stats = db.get_stats()

  col1, col2, col3 = st.columns(3)
  col1.metric("Channels Watched", stats["channels"])
  col2.metric("Videos Tracked", stats["videos"])
  col3.metric("Total Video Records", stats["records"])

elif menu == "Channels & Controls":
  st.header("Channels & Controls")

  st.subheader("Active Channels", divider="gray")
  dataframe = db.get_channels_df()
  st.dataframe(dataframe, hide_index=True, use_container_width=True)

  st.subheader("1. Add New Channel", divider="gray")
  new_handle = st.text_input("YouTube Handle (e.g., @mkbhd)")
  if st.button("Add Channel"):
    if new_handle:
      db.add_channel(new_handle)
      st.success(f"Added {new_handle} to the database. You can now scrape it!")
    else:
      st.error("Please enter a valid YouTube handle.")

  st.subheader("2. Trigger Scraping Action", divider="gray")
  handles_list = dataframe["handle"].tolist() if not dataframe.empty else []

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
          "Scraping all registered channels... "
          "This may take a while depending on limits."
        ):
          for h in handles_list:
            tracker.scrape_channel(h, limit=final_limit)
        st.success("Successfully completed scraping all channels!")
      else:
        with st.spinner(f"Scraping '{selected_option}'..."):
          tracker.scrape_channel(selected_option, limit=final_limit)
        st.success(f"Successfully scraped {selected_option}!")

elif menu == "History Log":
  st.header("History Log")

  st.subheader("Scrape Operations Log", divider="gray")
  st.write("Audit log of all tracking executions.")
  scrapes_df = db.get_scrapes_df()

  if scrapes_df.empty:
    st.info("No scrape operations recorded yet.")
  else:
    st.dataframe(scrapes_df, hide_index=True, use_container_width=True)

    st.subheader("Video Records Filter", divider="gray")
    formatted_options = ["All Records (Entire History)"] + [
      f"{row.scrape_id} ({row.started_at})" for row in scrapes_df.itertuples()
    ]

    selected_option = st.selectbox(
      "Filter records by scrape:", formatted_options
    )

    if selected_option == "All Records (Entire History)":
      st.write(
        "**Showing all historical records across every scrape execution.**"
      )
      videos_df = db.get_video_records_df()
    else:
      scrape_id = selected_option.split(" ")[0]
      st.write(
        "**Showing distinct video records mapped in scrape execution:** "
        f"`{scrape_id}`"
      )
      videos_df = db.get_scrape_videos_df(scrape_id)

    st.dataframe(
      videos_df,
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
        "status": "Status",
      },
      hide_index=True,
      use_container_width=True,
      height=800,
    )
