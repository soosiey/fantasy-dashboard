import requests
import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.paths import NFL_PLAYERS_PATH
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PAGE_SOURCES,
    PENDING_ROUTE_KEY,
    pop_pending_route,
    resolve_league_id,
    store_pending_route,
)

# Refresh the shared player cache without preventing the app from starting on failure.
try:
    SleeperClient(timeout=30.0).refresh_nfl_players_cache(NFL_PLAYERS_PATH)
except (OSError, TypeError, ValueError, requests.RequestException) as error:
    st.warning(f"Unable to refresh NFL player data: {error}")

authenticated = "sleeper_user" in st.session_state
league_id = resolve_league_id()
requested_user_id = st.query_params.get("user_id")
if requested_user_id is not None:
    st.session_state["user_id"] = str(requested_user_id)
user_id = st.session_state.get("user_id")
league_visibility = "visible" if authenticated and league_id else "hidden"

# Declare every route on every run so bookmarked pages remain recognizable.
start_page = st.Page(
    PAGE_SOURCES["login"],
    title="User Login",
    url_path="login",
    default=True,
    visibility="hidden" if authenticated else "visible",
)
leagues_page = st.Page(
    PAGE_SOURCES["leagues"],
    title="Leagues",
    url_path="leagues",
    visibility="visible" if authenticated and not league_id else "hidden",
)
overview_page = st.Page(
    PAGE_SOURCES["overview"],
    title="Overview",
    url_path="overview",
    visibility=league_visibility,
)
draft_results_page = st.Page(
    PAGE_SOURCES["draft-results"],
    title="Draft Results",
    url_path="draft-results",
    visibility=league_visibility,
)
transactions_page = st.Page(
    PAGE_SOURCES["transactions"],
    title="Transactions",
    url_path="transactions",
    visibility=league_visibility,
)
players_page = st.Page(
    PAGE_SOURCES["players"],
    title="Players",
    url_path="players",
    visibility=league_visibility,
)
matchups_page = st.Page(
    PAGE_SOURCES["matchups"],
    title="Matchups",
    url_path="matchups",
    visibility=league_visibility,
)
ranking_page = st.Page(
    PAGE_SOURCES["rankings"],
    title="Rankings",
    url_path="rankings",
    visibility=league_visibility,
)
analysis_page = st.Page(
    PAGE_SOURCES["analysis"],
    title="Statistics",
    url_path="analysis",
    visibility=league_visibility,
)
legacy_ranking_page = st.Page(
    "pages/ranking_legacy.py",
    title="Rankings",
    url_path="ranking",
    visibility="hidden",
)
legacy_draft_results_page = st.Page(
    "pages/draft_results_legacy.py",
    title="Draft Results",
    url_path="draft_results",
    visibility="hidden",
)
team_page = st.Page(
    PAGE_SOURCES["team"],
    title="Team",
    url_path="team",
    visibility=("visible" if authenticated and league_id and user_id else "hidden"),
)
pages_by_route = {
    "leagues": leagues_page,
    "overview": overview_page,
    "draft-results": draft_results_page,
    "transactions": transactions_page,
    "players": players_page,
    "matchups": matchups_page,
    "rankings": ranking_page,
    "analysis": analysis_page,
    "ranking": legacy_ranking_page,
    "draft_results": legacy_draft_results_page,
    "team": team_page,
}
page_route = st.navigation(
    [
        start_page,
        leagues_page,
        overview_page,
        draft_results_page,
        transactions_page,
        players_page,
        matchups_page,
        ranking_page,
        analysis_page,
        team_page,
        legacy_ranking_page,
        legacy_draft_results_page,
    ],
    position="hidden",
)

# Preserve a cold deep link through login, then return to the requested page.
if not authenticated and page_route.url_path:
    store_pending_route(page_route.url_path, st.query_params)
    st.switch_page(start_page)
if authenticated and PENDING_ROUTE_KEY in st.session_state:
    pending_route, pending_query = pop_pending_route()
    destination = pages_by_route.get(pending_route or "", leagues_page)
    st.switch_page(destination, query_params=pending_query)

# Entering Analysis changes the available navigation until the user explicitly exits.
if authenticated and league_id and page_route.url_path == "analysis":
    st.session_state[ANALYSIS_MODE_KEY] = True
analysis_mode = bool(st.session_state.get(ANALYSIS_MODE_KEY))
if analysis_mode and (not authenticated or not league_id):
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    analysis_mode = False
if analysis_mode and page_route.url_path not in {"analysis", "players"}:
    st.switch_page(analysis_page, query_params={"league_id": league_id})
if authenticated and not page_route.url_path:
    st.switch_page(overview_page if league_id else leagues_page)
if authenticated and page_route.url_path not in {"", "leagues"} and not league_id:
    st.switch_page(leagues_page)
if authenticated and page_route.url_path == "team" and not user_id:
    st.switch_page(overview_page, query_params={"league_id": league_id})

# Render an explicit sidebar so overview and analysis can behave as separate states.
with st.sidebar:
    if analysis_mode:
        st.page_link(
            analysis_page,
            label="Statistics",
        )
        st.page_link(players_page, label="Players")
    elif not authenticated:
        st.page_link(start_page, label="User Login")
    elif not league_id:
        st.page_link(leagues_page, label="Leagues")
    else:
        st.page_link(overview_page, label="Overview")
        st.page_link(draft_results_page, label="Draft Results")
        st.page_link(transactions_page, label="Transactions")
        st.page_link(players_page, label="Players")
        st.page_link(matchups_page, label="Matchups")
        st.page_link(ranking_page, label="Rankings")
        if user_id:
            st.page_link(team_page, label="Team")
        st.divider()
        st.page_link(
            analysis_page,
            label="Analysis",
            icon=":material/arrow_outward:",
            icon_position="right",
        )

# Hand control to the authenticated and context-valid page.
page_route.run()
