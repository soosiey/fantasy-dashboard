import streamlit as st

from fantasy_dashboard.data import clear_league_list, get_leagues

assert "sleeper_user" in st.session_state, "No user found for leagues to show"
user = st.session_state["sleeper_user"]
user_id = user.user_id

# Render each available league as a full-width navigation target.
title_column, refresh_column = st.columns([8, 1], vertical_alignment="center")
with title_column:
    st.title("Leagues")
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-leagues",
        help="Reload leagues from Sleeper",
        width="content",
    )

if force_refresh:
    clear_league_list(user_id, "2026", "nfl")
    st.rerun()

st.caption("Select a league to view.")
leagues = get_leagues(user_id, "2026", "nfl")
for league in leagues.leagues:
    st.page_link(
        "pages/overview.py",
        label=f"**{league.name}**",
        icon="🏈",
        query_params={"league_id": league.league_id},
        width="stretch",
    )

# Keep account-level actions anchored at the bottom of the page.
with st.bottom:
    reset = st.button("Log Out")

if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()
