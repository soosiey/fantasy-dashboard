import requests
import streamlit as st

from fantasy_dashboard.components.matchup_board import (
    PlayerComparisonSelection,
    render_matchup_carousel,
)
from fantasy_dashboard.components.player_comparison import show_player_comparison
from fantasy_dashboard.components.player_details import show_player_details
from fantasy_dashboard.data import (
    clear_matchup_data,
    get_league,
    get_league_users,
    get_nfl_players,
    get_player_stats,
    get_rosters,
    get_weekly_matchups,
)
from fantasy_dashboard.matchups import build_head_to_head_matchups

league_id = st.query_params.get("league_id")
if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state.get("league_id")

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

league = get_league(league_id)
stats_season = league.season

# Keep the week selector aligned opposite the page title.
title_column, week_column, refresh_column = st.columns(
    [6, 2, 0.5], vertical_alignment="center"
)
with title_column:
    st.title("Matchups")
with week_column:
    selected_week = st.selectbox(
        "Week",
        range(1, 19),
        format_func=lambda week: f"Week {week}",
    )
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-matchups",
        help="Reload this week's scores and lineups from Sleeper",
        width="content",
    )

if force_refresh:
    clear_matchup_data(
        league_id,
        selected_week,
        stats_season,
        league.season_type,
    )
    st.rerun()

# Load the selected week's lineups and resolve their team and player identities.
weekly_matchups = get_weekly_matchups(league_id, selected_week)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
players = get_nfl_players()
try:
    stats_by_player_id = get_player_stats(
        stats_season,
        league.season_type,
        selected_week,
    )
except (requests.RequestException, TypeError, ValueError):
    stats_by_player_id = {}
    st.warning("Player statistics could not be loaded; scores default to zero.")

st.write(f"League: {league.name}")
matchups = build_head_to_head_matchups(
    weekly_matchups.matchups,
    league,
    rosters.rosters,
    teams.users,
    players,
    stats_by_player_id,
)
current_user = st.session_state.get("sleeper_user")
selected_player_id = render_matchup_carousel(
    matchups,
    current_user.user_id if current_user is not None else None,
    context_key=f"{league_id}-{selected_week}",
)

if isinstance(selected_player_id, PlayerComparisonSelection):
    show_player_comparison(
        selected_player_id.left_player_id,
        selected_player_id.right_player_id,
        players,
        stats_by_player_id,
        league.scoring_settings,
    )
elif selected_player_id:
    selected_player = players.get(str(selected_player_id))
    if selected_player is None:
        st.warning("That player could not be found in the local player cache.")
    else:
        show_player_details(
            str(selected_player_id),
            selected_player,
            stats_season,
            league.season_type,
            league.scoring_settings,
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
