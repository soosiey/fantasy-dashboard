import requests
import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.paths import NFL_PLAYERS_PATH

# Refresh the shared player cache without preventing the app from starting on failure.
try:
    SleeperClient(timeout=30.0).refresh_nfl_players_cache(NFL_PLAYERS_PATH)
except (OSError, TypeError, ValueError, requests.RequestException) as error:
    st.warning(f"Unable to refresh NFL player data: {error}")

start_page = st.Page("pages/start.py", title="User Login", default=True)

# Build navigation around the user's login and league-selection state.
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

    ranking_page = st.Page(
        "pages/ranking.py",
        title="Rankings",
        visibility="visible" if st.session_state.get("league_id") else "hidden",
    )

    matchups_page = st.Page(
        "pages/matchups.py",
        title="Matchups",
        visibility="visible" if st.session_state.get("league_id") else "hidden",
    )

    team_page = st.Page(
        "pages/team.py",
        title="Team",
        visibility="visible" if st.session_state.get("team_id") else "hidden",
    )

    page_route = st.navigation(
        [leagues_page, overview_page, matchups_page, ranking_page, team_page]
    )

# Hand control to the page selected by Streamlit's navigation router.
page_route.run()
