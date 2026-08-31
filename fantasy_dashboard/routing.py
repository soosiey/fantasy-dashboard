from collections.abc import Mapping
from typing import Any

import streamlit as st

PAGE_SOURCES = {
    "login": "pages/start.py",
    "leagues": "pages/leagues.py",
    "overview": "pages/overview.py",
    "draft-results": "pages/draft_results.py",
    "transactions": "pages/transactions.py",
    "players": "pages/players.py",
    "matchups": "pages/matchups.py",
    "rankings": "pages/ranking.py",
    "analysis": "pages/analysis.py",
    "league-predictions": "pages/league_predictions.py",
    "comparison": "pages/comparison.py",
    "graphs": "pages/graphs.py",
    "graph": "pages/graph.py",
    "stats": "pages/stats.py",
    "performance": "pages/performance.py",
    "news": "pages/news.py",
    "team": "pages/team.py",
}

PENDING_ROUTE_KEY = "_pending_route"
PENDING_QUERY_KEY = "_pending_query_params"
ANALYSIS_MODE_KEY = "_analysis_mode"
PLAYER_STATS_MODE_KEY = "_player_stats_mode"
PLAYER_STATS_PENDING_KEY = "_player_stats_transition_pending"


# Resolve durable URL context first, then retain it across sidebar navigation.
def resolve_context_id(query_key: str, session_key: str | None = None) -> str | None:
    state_key = session_key or query_key
    query_value = st.query_params.get(query_key)
    value = query_value if query_value is not None else st.session_state.get(state_key)
    if value in (None, ""):
        return None

    normalized_value = str(value)
    st.session_state[state_key] = normalized_value
    if st.query_params.get(query_key) != normalized_value:
        st.query_params[query_key] = normalized_value
    return normalized_value


def resolve_league_id() -> str | None:
    return resolve_context_id("league_id")


def resolve_user_id() -> str | None:
    return resolve_context_id("user_id")


# Update selected view state without discarding the page's identity parameters.
def sync_query_params(**values: Any) -> None:
    for key, value in values.items():
        if value in (None, "", False):
            if key in st.query_params:
                st.query_params.pop(key)
            continue
        normalized_value = str(value)
        if st.query_params.get(key) != normalized_value:
            st.query_params[key] = normalized_value


def store_pending_route(route: str, query_params: Mapping[str, Any]) -> None:
    st.session_state[PENDING_ROUTE_KEY] = route
    st.session_state[PENDING_QUERY_KEY] = dict(query_params)


def pop_pending_route() -> tuple[str | None, dict[str, Any]]:
    route = st.session_state.pop(PENDING_ROUTE_KEY, None)
    query_params = st.session_state.pop(PENDING_QUERY_KEY, {})
    return (
        str(route) if route else None,
        dict(query_params) if isinstance(query_params, Mapping) else {},
    )


# Keep every directly addressed page behind login while retaining its destination.
def require_authentication(route: str) -> Any:
    user = st.session_state.get("sleeper_user")
    if user is not None:
        return user

    store_pending_route(route, st.query_params)
    st.switch_page(PAGE_SOURCES["login"])
