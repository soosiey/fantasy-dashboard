import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.components.playoff_bracket import render_playoff_bracket
from fantasy_dashboard.components.ranking_table import render_ranking_table
from fantasy_dashboard.playoffs import build_playoff_rounds
from fantasy_dashboard.standings import build_standings

# Restore the API client and selected league across page navigation.
if "client" not in st.session_state:
    client = SleeperClient()
else:
    client = st.session_state.get("client")

league_id = st.query_params.get("league_id")
if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state.get("league_id")

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

# Load league results and join each roster to its displayed team identity.
league = client.get_single_league(league_id)
rosters = client.get_all_rosters(league_id)
teams = client.get_all_users(league_id)

# Keep the regular-season/playoff switch aligned at the top right of the page.
title_column, view_column = st.columns([5, 3], vertical_alignment="center")
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

st.write(f"League: {league.name}")

# Render either the standings table or Sleeper's left-to-right playoff bracket.
if ranking_view == "🏆 Playoffs":
    bracket = client.get_winners_bracket(league_id)
    playoff_rounds = build_playoff_rounds(
        bracket.matchups,
        rosters.rosters,
        teams.users,
    )
    render_playoff_bracket(playoff_rounds)
else:
    standings = build_standings(rosters.rosters, teams.users)
    render_ranking_table(standings)

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
