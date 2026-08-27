from pathlib import Path

import requests
import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient

NFL_PLAYERS_PATH = Path(__file__).with_name("nfl_players.json")

try:
    SleeperClient(timeout=30.0).refresh_nfl_players_cache(NFL_PLAYERS_PATH)
except (OSError, TypeError, ValueError, requests.RequestException) as error:
    st.warning(f"Unable to refresh NFL player data: {error}")

start_page = st.Page("pages/start.py", title="User Login", default=True)


if "sleeper_user" not in st.session_state:
    page_route = st.navigation([start_page])
else:
    league_id = st.query_params.get("league_id")

    if league_id:
        st.session_state["league_id"] = str(league_id)

    leagues_page = st.Page(
        "pages/leagues.py",
        title="Leagues",
        default=True,
        visibility="hidden" if st.session_state.get("league_id") else "visible",
    )

    overview_page = st.Page(
        "pages/overview.py",
        title="Overview",
        visibility="visible" if st.session_state.get("league_id") else "hidden",
    )

    team_page = st.Page(
        "pages/team.py",
        title="Team",
        visibility="visible" if st.session_state.get("team_id") else "hidden",
    )

    page_route = st.navigation([leagues_page, overview_page, team_page])

page_route.run()
