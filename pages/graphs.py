import streamlit as st

from fantasy_dashboard.components.comparison_selection import (
    render_comparison_sidebar,
)
from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.graph_player_picker import (
    render_graph_player_picker,
)
from fantasy_dashboard.data import (
    get_data_update,
    get_league,
    get_league_users,
    get_nfl_players,
    get_rosters,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PLAYER_STATS_MODE_KEY,
    PLAYER_STATS_PENDING_KEY,
    require_authentication,
    resolve_league_id,
)

require_authentication("graphs")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

if st.session_state.pop(PLAYER_STATS_PENDING_KEY, False):
    selected_player_id = st.session_state.get("graph_player_id")
    graph_query_params = {"league_id": league_id}
    if selected_player_id:
        graph_query_params["player_id"] = str(selected_player_id)
    st.switch_page("pages/graph.py", query_params=graph_query_params)

if not st.session_state.get(ANALYSIS_MODE_KEY):
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Single Player Selection")

league = get_league(league_id)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
nfl_players = get_nfl_players()

single_player_tab, comparison_stats_tab = st.tabs(
    ["Single Player Stats", "Comparison Stats"]
)
with single_player_tab:
    render_graph_player_picker(league_id, league, rosters, teams, nfl_players)
with comparison_stats_tab:
    pass

render_comparison_sidebar(nfl_players, league_id)
render_data_disclaimer(
    get_data_update("nfl_players"),
    get_data_update("rosters", league_id),
)

with st.bottom:
    back_to_overview = st.button("Back to Overview")

if back_to_overview:
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.switch_page(
        "pages/overview.py",
        query_params={"league_id": league_id},
    )
