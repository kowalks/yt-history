"""Streamlit dashboard for YouTube History Tracker.

This module renders the frontend relying on the internal db API.
"""

import streamlit as st

st.set_page_config(
  page_title="YouTube History Tracker", page_icon="🕵️‍♂️", layout="wide"
)

st.markdown(
  """
<style>
body {
    font-size: 20px !important;
}
p {
    font-size: 20px !important;
}
</style>
""",
  unsafe_allow_html=True,
)

# Define Pages
pg = st.navigation(
  [
    st.Page("views/overview.py", title="Dashboard", icon="🏠"),
    st.Page("views/channels.py", title="Channels & Controls", icon="📺"),
    st.Page("views/history.py", title="History Log", icon="📜"),
  ]
)

pg.run()
