import streamlit as st

from fantasy_dashboard.components.player_performance_page import (
    render_player_performance,
)
from fantasy_dashboard.data import get_nfl_players
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PLAYER_STATS_MODE_KEY,
    require_authentication,
    resolve_context_id,
    resolve_league_id,
)

require_authentication("performance")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

player_id = resolve_context_id("player_id", "graph_player_id")
if player_id is None:
    st.warning("Select a player first.")
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page("pages/graphs.py", query_params={"league_id": league_id})

if not st.session_state.get(PLAYER_STATS_MODE_KEY):
    st.session_state[PLAYER_STATS_MODE_KEY] = True
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 115rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Performance")

players = get_nfl_players()
player = players.get(player_id)
if player is None:
    st.warning("That player could not be found in the local player cache.")
else:
    render_player_performance(league_id, player_id, players, player)

with st.bottom:
    back_to_analysis = st.button("Back to Analysis")

if back_to_analysis:
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page(
        "pages/graphs.py",
        query_params={"league_id": league_id},
    )
