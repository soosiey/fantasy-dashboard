import streamlit as st

# Preserve bookmarks created before public routes switched to hyphenated names.
st.switch_page("pages/draft_results.py", query_params=dict(st.query_params))
