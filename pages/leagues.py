from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.data import (
    clear_league_list,
    get_current_nfl_season,
    get_data_update,
    get_leagues,
)

assert "sleeper_user" in st.session_state, "No user found for leagues to show"
user = st.session_state["sleeper_user"]
user_id = user.user_id

# Prefer Sleeper's active season, with a calendar fallback during API outages.
try:
    current_season = int(get_current_nfl_season())
except (requests.RequestException, KeyError, TypeError, ValueError):
    today = datetime.now(ZoneInfo("America/New_York")).date()
    current_season = today.year if today.month >= 3 else today.year - 1
    st.warning("The current NFL season could not be detected from Sleeper.")

season_options = [str(current_season - offset) for offset in range(3)]

# Render the season filter and each league as a full-width navigation target.
title_column, season_column, refresh_column = st.columns(
    [6, 2, 0.5], vertical_alignment="center"
)
with title_column:
    st.title("Leagues")
with season_column:
    selected_season = st.selectbox("Season", season_options)
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-leagues",
        help="Reload leagues from Sleeper",
        width="content",
    )

if force_refresh:
    clear_league_list(user_id, selected_season, "nfl")
    st.rerun()

st.caption("Select a league to view.")
leagues = get_leagues(user_id, selected_season, "nfl")
if leagues is None or not leagues.leagues:
    st.info(f"No leagues found for the {selected_season} season.")
else:
    for league in leagues.leagues:
        st.page_link(
            "pages/overview.py",
            label=f"**{league.name}**",
            icon="🏈",
            query_params={"league_id": league.league_id},
            width="stretch",
        )

render_data_disclaimer(get_data_update("leagues", user_id, selected_season, "nfl"))

# Keep account-level actions anchored at the bottom of the page.
with st.bottom:
    reset = st.button("Log Out")

if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()
