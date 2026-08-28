import streamlit as st

# Preserve bookmarks created before the rankings route became plural.
st.switch_page("pages/ranking.py", query_params=dict(st.query_params))
