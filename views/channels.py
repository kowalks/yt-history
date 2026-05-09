import streamlit as st
import db
import tracker


def show():
  st.header("Channels & Controls")

  st.subheader("Active Channels", divider="gray")
  dataframe = db.get_channels_df()

  # Background Activity Check
  active_scrapes = db.get_active_sessions_df()
  if not active_scrapes.empty:
    with st.status("🛠️ Intelligence Gathering in Progress...", expanded=False):
      for _, row in active_scrapes.iterrows():
        st.write(f"Session `{row['id'][:8]}` active...")
      if st.button("Refresh UI Status"):
        st.rerun()

  if not dataframe.empty:
    if st.button("🚀 Scrape All Channels", use_container_width=True):
      handles_list = dataframe["handle"].tolist()
      tracker.start_background_scrape(handles_list)
      st.toast("Intelligence gathering started for all channels!")
      st.rerun()

  if dataframe.empty:
    st.info("No channels tracked yet. Add one below!")
  else:
    # Header
    hcol1, hcol2, hcol3, hcol4, hcol5, hcol6 = st.columns([2, 2, 1, 2, 0.5, 0.5])
    hcol1.write("**Name**")
    hcol2.write("**Handle**")
    hcol3.write("**Videos**")
    hcol4.write("**Added At**")
    hcol5.write("**Run**")
    hcol6.write("**Del**")

    for row in dataframe.itertuples():
      rcol1, rcol2, rcol3, rcol4, rcol5, rcol6 = st.columns(
        [2, 2, 1, 2, 0.5, 0.5]
      )
      rcol1.write(row.name or "Unknown")
      rcol2.write(row.handle)
      rcol3.write(f"{row.video_count}")
      rcol4.write(row.added_at)

      if rcol5.button("🚀", key=f"run_{row.handle}", help=f"Scrape {row.handle}"):
        tracker.start_background_scrape([row.handle])
        st.toast(f"Started scrape for {row.handle}")
        st.rerun()

      if rcol6.button(
        "🗑️", key=f"del_{row.handle}", help=f"Remove {row.handle}"
      ):
        db.remove_channel(row.handle)
        st.rerun()

  st.subheader("Add New Channel", divider="gray")
  new_handle = st.text_input("YouTube Handle (e.g., @mkbhd)")
  if st.button("Add Channel"):
    if new_handle:
      # Normalize input
      normalized = db.normalize_handle(new_handle)
      with st.spinner(f"Validating {normalized}..."):
        try:
          channel_name = tracker.get_channel_name(normalized)
          if channel_name is None:
             st.error(f"Could not find a valid YouTube channel for `{normalized}`. Please check the handle.")
          else:
             db.add_channel(normalized, name=channel_name)
             st.success(f"Added {channel_name} ({normalized}) to the database!")
             st.rerun()
        except Exception as e:
          st.error(f"Error adding channel: {str(e)}")
    else:
      st.error("Please enter a valid YouTube handle.")

  st.divider()
  with st.expander("☢️ Danger Zone"):
    st.warning("This will permanently delete all channels, videos, and scrape history.")
    
    if "confirm_reset" not in st.session_state:
        st.session_state.confirm_reset = False

    if not st.session_state.confirm_reset:
        if st.button("Purge All Data & Reset Database", type="primary"):
            st.session_state.confirm_reset = True
            st.rerun()
    else:
        st.error("🚨 ARE YOU ABSOLUTELY SURE? This operation is irreversible.")
        col_c1, col_c2 = st.columns(2)
        if col_c1.button("🔥 YES, RESET EVERYTHING", type="primary", use_container_width=True):
            db.reset_db()
            st.session_state.confirm_reset = False
            st.success("Database has been reset!")
            st.rerun()
        if col_c2.button("❌ No, cancel", use_container_width=True):
            st.session_state.confirm_reset = False
            st.rerun()


if __name__ == "__main__":
  show()
