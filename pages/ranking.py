import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.playoff_bracket import render_playoff_bracket
from fantasy_dashboard.components.ranking_table import render_ranking_table
from fantasy_dashboard.data import (
    clear_ranking_data,
    get_data_update,
    get_league,
    get_league_users,
    get_losers_bracket,
    get_rosters,
    get_winners_bracket,
)
from fantasy_dashboard.playoffs import build_playoff_rounds
from fantasy_dashboard.standings import build_standings

league_id = st.query_params.get("league_id")
if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state.get("league_id")

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

# Keep the regular-season/playoff switch aligned at the top right of the page.
title_column, view_column, refresh_column = st.columns(
    [6, 4, 0.5], vertical_alignment="center"
)
with title_column:
    st.title("User Rankings")
with view_column:
    ranking_view = st.segmented_control(
        "Ranking view",
        ["📊 Regular Season", "🏆 Playoffs"],
        default="📊 Regular Season",
        label_visibility="collapsed",
        width="stretch",
    )
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-rankings",
        help="Reload standings and playoff brackets from Sleeper",
        width="content",
    )

if force_refresh:
    clear_ranking_data(league_id)
    st.rerun()

# Load league results and join each roster to its displayed team identity.
league = get_league(league_id)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)

st.write(f"League: {league.name}")

# Render either the standings table or Sleeper's left-to-right playoff bracket.
if ranking_view == "🏆 Playoffs":
    st.header("Winners Bracket")
    bracket = get_winners_bracket(league_id)
    playoff_rounds = build_playoff_rounds(
        bracket.matchups,
        rosters.rosters,
        teams.users,
    )
    render_playoff_bracket(playoff_rounds)
    st.header("Losers Bracket")
    bracket = get_losers_bracket(league_id)
    playoff_rounds = build_playoff_rounds(
        bracket.matchups,
        rosters.rosters,
        teams.users,
    )
    render_playoff_bracket(playoff_rounds)
else:
    standings = build_standings(rosters.rosters, teams.users)
    render_ranking_table(standings)

ranking_updates = [get_data_update("rosters", league_id)]
if ranking_view == "🏆 Playoffs":
    ranking_updates.extend(
        [
            get_data_update("winners_bracket", league_id),
            get_data_update("losers_bracket", league_id),
        ]
    )
render_data_disclaimer(*ranking_updates)

# Keep league and account navigation available beneath the standings.
with st.bottom:
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if league_change:
    st.session_state.pop("league_id")
    if "league_id" in st.query_params:
        st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()
