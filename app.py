from importlib import reload

import requests
import streamlit as st

import about.version as version_module
from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.data import (
    PLAYER_CATALOG_MAX_AGE,
    get_manual_refresh_cooldown_remaining,
    get_nfl_schedule,
    has_live_nfl_game,
    record_manual_refresh,
    refresh_current_week_input_data,
)
from fantasy_dashboard.paths import NFL_PLAYERS_PATH
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PAGE_SOURCES,
    PENDING_ROUTE_KEY,
    PLAYER_STATS_MODE_KEY,
    pop_pending_route,
    resolve_league_id,
    store_pending_route,
)

# Streamlit hot reloads app.py but can retain imported modules from the previous
# deployment. Reload the tiny version module so the release badge tracks GitHub.
VERSION = reload(version_module).VERSION

# Refresh the shared player cache without preventing the app from starting on failure.
try:
    SleeperClient(timeout=30.0).refresh_nfl_players_cache(
        NFL_PLAYERS_PATH,
        max_age=PLAYER_CATALOG_MAX_AGE,
    )
except (OSError, TypeError, ValueError, requests.RequestException) as error:
    st.warning(f"Unable to refresh NFL player data: {error}")

authenticated = "sleeper_user" in st.session_state
league_id = resolve_league_id()
requested_user_id = st.query_params.get("user_id")
if requested_user_id is not None:
    st.session_state["user_id"] = str(requested_user_id)
user_id = st.session_state.get("user_id")
league_visibility = "visible" if authenticated and league_id else "hidden"

# Refresh stale current-week inputs after login while retaining disk fallbacks.
game_active = False
if authenticated:
    try:
        current_season, current_season_type, current_week = (
            refresh_current_week_input_data()
        )
        game_active = has_live_nfl_game(
            get_nfl_schedule(current_season, current_season_type),
            current_week,
        )
    except (OSError, TypeError, ValueError, requests.RequestException) as error:
        st.warning(f"Unable to refresh current-week player data: {error}")

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
trade_analysis_page = st.Page(
    PAGE_SOURCES.get("trade-analysis", "pages/trade_analysis.py"),
    title="Trade Analysis",
    url_path="trade-analysis",
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
league_predictions_page = st.Page(
    # Streamlit can retain an older imported routing module during a code hot reload.
    PAGE_SOURCES.get("league-predictions", "pages/league_predictions.py"),
    title="League Predictions",
    url_path="league-predictions",
    visibility=league_visibility,
)
regression_page = st.Page(
    PAGE_SOURCES.get("regression", "pages/regression.py"),
    title="Regression",
    url_path="regression",
    visibility=league_visibility,
)
comparison_page = st.Page(
    PAGE_SOURCES["comparison"],
    title="Comparison",
    url_path="comparison",
    visibility=league_visibility,
)
graphs_page = st.Page(
    PAGE_SOURCES["graphs"],
    title="Single Player Selection",
    url_path="graphs",
    visibility=league_visibility,
)
graph_page = st.Page(
    PAGE_SOURCES["graph"],
    title="Graph",
    url_path="graph",
    visibility=league_visibility,
)
stats_page = st.Page(
    PAGE_SOURCES["stats"],
    title="Stats",
    url_path="stats",
    visibility=league_visibility,
)
performance_page = st.Page(
    PAGE_SOURCES["performance"],
    title="Performance",
    url_path="performance",
    visibility=league_visibility,
)
news_page = st.Page(
    PAGE_SOURCES["news"],
    title="News",
    url_path="news",
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
    "trade-analysis": trade_analysis_page,
    "rankings": ranking_page,
    "analysis": analysis_page,
    "league-predictions": league_predictions_page,
    "regression": regression_page,
    "comparison": comparison_page,
    "graphs": graphs_page,
    "graph": graph_page,
    "stats": stats_page,
    "performance": performance_page,
    "news": news_page,
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
        trade_analysis_page,
        ranking_page,
        analysis_page,
        league_predictions_page,
        regression_page,
        comparison_page,
        graphs_page,
        graph_page,
        stats_page,
        performance_page,
        news_page,
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
if (
    authenticated
    and league_id
    and page_route.url_path
    in {
        "analysis",
        "trade-analysis",
        "league-predictions",
        "regression",
        "comparison",
        "graphs",
    }
):
    st.session_state[ANALYSIS_MODE_KEY] = True
if (
    authenticated
    and league_id
    and page_route.url_path in {"graph", "stats", "performance", "news"}
):
    st.session_state[PLAYER_STATS_MODE_KEY] = True
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
player_stats_mode = bool(st.session_state.get(PLAYER_STATS_MODE_KEY))
if player_stats_mode and (not authenticated or not league_id):
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    player_stats_mode = False
analysis_mode = bool(st.session_state.get(ANALYSIS_MODE_KEY))
if analysis_mode and (not authenticated or not league_id):
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    analysis_mode = False
if player_stats_mode and page_route.url_path not in {
    "graph",
    "stats",
    "performance",
    "news",
}:
    st.switch_page(graph_page, query_params={"league_id": league_id})
if analysis_mode and page_route.url_path not in {
    "analysis",
    "league-predictions",
    "regression",
    "players",
    "matchups",
    "trade-analysis",
    "comparison",
    "graphs",
}:
    st.switch_page(analysis_page, query_params={"league_id": league_id})
if authenticated and not page_route.url_path:
    st.switch_page(overview_page if league_id else leagues_page)
if authenticated and page_route.url_path not in {"", "leagues"} and not league_id:
    st.switch_page(leagues_page)
if authenticated and page_route.url_path == "team" and not user_id:
    st.switch_page(overview_page, query_params={"league_id": league_id})


# Render this before page-owned controls so it remains their leftmost action.
def request_current_week_refresh() -> None:
    st.session_state["_refresh_current_week_input_data"] = True


def format_cooldown(remaining_seconds: float) -> str:
    total_minutes = max(1, int((remaining_seconds + 59) // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


if st.session_state.pop("_manual_refresh_success", False):
    st.toast("Current-week actual stats refreshed.")

refresh_cooldown = get_manual_refresh_cooldown_remaining()
refresh_disabled = refresh_cooldown.total_seconds() > 0
refresh_help = "Pull fresh actual stats for the current NFL week"
if refresh_disabled:
    refresh_help = (
        "Manual refresh available in "
        f"{format_cooldown(refresh_cooldown.total_seconds())}"
    )

if authenticated:
    with st.bottom:
        st.button(
            "Refresh Current Week",
            key="refresh-current-week-input-data",
            help=refresh_help,
            disabled=refresh_disabled,
            on_click=request_current_week_refresh,
        )

if st.session_state.pop("_refresh_current_week_input_data", False):
    remaining = get_manual_refresh_cooldown_remaining()
    if remaining.total_seconds() > 0:
        st.warning(
            "Manual refresh is on cooldown for "
            f"{format_cooldown(remaining.total_seconds())}."
        )
    else:
        try:
            with st.spinner("Refreshing current-week actual stats..."):
                refresh_current_week_input_data(force=True)
            record_manual_refresh()
            st.session_state["_manual_refresh_success"] = True
            st.rerun()
        except (OSError, TypeError, ValueError, requests.RequestException) as error:
            st.warning(f"Unable to refresh current-week player data: {error}")

# Render an explicit sidebar so overview and analysis can behave as separate states.
with st.sidebar:
    if player_stats_mode:
        st.page_link(graph_page, label="Graph")
        st.page_link(stats_page, label="Stats")
        st.page_link(performance_page, label="Performance")
        st.page_link(news_page, label="News")
    elif analysis_mode:
        st.page_link(
            analysis_page,
            label="Statistics",
        )
        st.page_link(players_page, label="Players")
        st.page_link(matchups_page, label="Matchups")
        st.page_link(comparison_page, label="Comparison")
        st.page_link(graphs_page, label="Single Player Selection")
        st.page_link(league_predictions_page, label="League Predictions")
        st.page_link(regression_page, label="Regression")
        st.page_link(trade_analysis_page, label="Trade Analysis")
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

# Keep live-game and release status visible independently of the active app state.
game_status_class = "active" if game_active else "inactive"
game_status_description = (
    "An NFL game is live; dashboard data uses live refresh intervals."
    if game_active
    else "No NFL game is currently live; standard refresh intervals apply."
)
st.markdown(
    f"""
    <style>
    .game-status-indicator {{
        position: fixed;
        right: 0.9rem;
        top: 3.6rem;
        z-index: 10000;
        display: inline-flex;
        align-items: center;
        gap: 0.42rem;
        color: var(--text-color);
        background: color-mix(in srgb, var(--background-color) 92%, transparent);
        border: 1px solid color-mix(in srgb, var(--text-color) 18%, transparent);
        border-radius: 999px;
        padding: 0.3rem 0.62rem;
        font-size: 0.78rem;
        font-weight: 600;
        line-height: 1rem;
        pointer-events: none;
    }}
    .game-status-light {{
        width: 0.58rem;
        height: 0.58rem;
        flex: 0 0 0.58rem;
        border-radius: 50%;
        background: #9ca3af;
    }}
    .game-status-indicator.active .game-status-light {{
        background: #22c55e;
        box-shadow: 0 0 0.38rem rgba(34, 197, 94, 0.8);
    }}
    .app-version-indicator {{
        position: fixed;
        right: 0.9rem;
        bottom: 0.7rem;
        z-index: 10000;
        color: var(--text-color);
        background: color-mix(in srgb, var(--background-color) 88%, transparent);
        border: 1px solid color-mix(in srgb, var(--text-color) 18%, transparent);
        border-radius: 999px;
        padding: 0.18rem 0.5rem;
        font-size: 0.72rem;
        line-height: 1rem;
        opacity: 0.65;
        pointer-events: none;
    }}
    </style>
    <div
        class="game-status-indicator {game_status_class}"
        aria-label="{game_status_description}"
        title="{game_status_description}"
        data-game-active="{str(game_active).lower()}"
    >
        <span class="game-status-light" aria-hidden="true"></span>
        <span>Game Active</span>
    </div>
    <div class="app-version-indicator" aria-label="Application version">
        v{VERSION}
    </div>
    """,
    unsafe_allow_html=True,
)

# Hand control to the authenticated and context-valid page.
page_route.run()
