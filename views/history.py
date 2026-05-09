import streamlit as st

import db


def show():
  st.header("History Log")

  col1, col2 = st.columns([1, 2])

  with col1:
    st.subheader("Scrape Operations Log", divider="gray")
    st.write("Audit log of all tracking executions.")
    scrapes_df = db.get_scrapes_df()

    if scrapes_df.empty:
      st.info("No scrape operations recorded yet.")
    else:
      st.dataframe(
        scrapes_df,
        column_config={
          "scrape_id": st.column_config.TextColumn("ID", width="small"),
          "started_at": "Started At",
          "status": "Status",
          "total_videos": "Videos",
          "new_records": "Changes",
          "channels_count": "Channels",
        },
        hide_index=True,
        width="stretch",
      )

  with col2:
    if not scrapes_df.empty:
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

      # Optional: Highlight changes in the history log too
      changes_df = db.get_metadata_changes_df()
      changes_ids = (
        changes_df["record_id"].tolist() if not changes_df.empty else []
      )

      if not videos_df.empty:
        videos_df["Alert"] = videos_df["record_id"].apply(
          lambda x: "⚠️ Modified" if x in changes_ids else ""
        )

      st.dataframe(
        videos_df,
        column_config={
          "Alert": st.column_config.TextColumn("Alert", width="small"),
          "record_id": st.column_config.TextColumn("Version ID", width="small"),
          "thumbnail_url": st.column_config.ImageColumn("Thumbnail"),
          "video_url": st.column_config.LinkColumn(
            "Video Link", display_text=r"https://youtube\.com/watch\?v=(.*)"
          ),
          "channel_name": "Channel",
          "channel_handle": "Handle",
          "title": "Title",
          "duration_sec": st.column_config.NumberColumn(
            "Duration (s)", format="%d"
          ),
          "status": "Status",
        },
        hide_index=True,
        width="stretch",
        height=700,
      )


if __name__ == "__main__":
  show()
