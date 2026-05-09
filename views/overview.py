import streamlit as st

import db


def show():
  st.header("Intelligence Dashboard")

  # Background Activity Check — query the session table directly
  active_scrapes = db.get_active_sessions_df()
  if not active_scrapes.empty:
    with st.status("🛠️ Intelligence Gathering in Progress...", expanded=True):
      for _, row in active_scrapes.iterrows():
        st.write(
          f"Scrape Session `{row['id'][:8]}` started at `{row['started_at']}`"
        )
      st.button("Refresh Progress")

  stats = db.get_stats()

  col1, col2, col3 = st.columns(3)
  col1.metric("Channels", stats["channels"])
  col2.metric("Videos", stats["videos"])
  col3.metric("Records", stats["records"])

  st.divider()

  st.subheader("System Status")
  st.info(
    "Monitoring active. New video metadata will be captured "
    "during the next scrape."
  )

  st.divider()

  st.subheader("⚠️ Recent Intelligence Alerts")
  changes_df = db.get_metadata_changes_df()

  if changes_df.empty:
    st.success("No significant metadata changes detected in recent scrapes.")
  else:
    st.warning(f"Detected {len(changes_df)} videos with modified metadata!")
    # Show simplified view of changes
    st.dataframe(
      changes_df,
      column_config={
        "record_id": st.column_config.TextColumn("Version ID", width="small"),
        "channel_name": "Channel",
        "title": "Current Title",
        "prev_title": "Previous Title",
        "status": "Current Status",
        "prev_status": "Previous Status",
      },
      hide_index=True,
      width="stretch",
    )


if __name__ == "__main__":
  show()
