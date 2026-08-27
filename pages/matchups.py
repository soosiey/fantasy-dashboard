import json

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.components.matchup_board import render_matchup_carousel
from fantasy_dashboard.matchups import build_head_to_head_matchups
from fantasy_dashboard.paths import NFL_PLAYERS_PATH

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

# Keep the week selector aligned opposite the page title.
title_column, week_column = st.columns([5, 2], vertical_alignment="center")
with title_column:
    st.title("Matchups")
with week_column:
    selected_week = st.selectbox(
        "Week",
        range(1, 19),
        format_func=lambda week: f"Week {week}",
    )

# Load the selected week's lineups and resolve their team and player identities.
league = client.get_single_league(league_id)
weekly_matchups = client.get_matchups(league_id, selected_week)
rosters = client.get_all_rosters(league_id)
teams = client.get_all_users(league_id)
with NFL_PLAYERS_PATH.open(encoding="utf-8") as player_file:
    players = json.load(player_file)

st.write(f"League: {league.name}")
matchups = build_head_to_head_matchups(
    weekly_matchups.matchups,
    league,
    rosters.rosters,
    teams.users,
    players,
)
current_user = st.session_state.get("sleeper_user")
render_matchup_carousel(
    matchups,
    current_user.user_id if current_user is not None else None,
    context_key=f"{league_id}-{selected_week}",
)

# Keep league and account navigation available beneath the weekly matchups.
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
