import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.matchup_board import (
    PlayerComparisonSelection,
    render_matchup_carousel,
)
from fantasy_dashboard.components.player_comparison import show_player_comparison
from fantasy_dashboard.components.player_details import show_player_details
from fantasy_dashboard.data import (
    clear_matchup_data,
    clear_projected_player_data,
    get_data_update,
    get_default_nfl_week,
    get_league,
    get_league_users,
    get_nfl_players,
    get_nfl_schedule,
    get_player_stats,
    get_projected_player_stats,
    get_rosters,
    get_weekly_matchups,
)
from fantasy_dashboard.matchups import (
    build_head_to_head_matchups,
    build_week_opponents,
)

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
try:
    current_week = get_default_nfl_week(stats_season)
except (requests.RequestException, KeyError, TypeError, ValueError):
    current_week = 1

# Group the matchup filters opposite the title with enough room for the
# Actual/Predicted selector to remain on one horizontal line.
title_column, filter_column = st.columns(
    [6, 3], vertical_alignment="center"
)
with title_column:
    st.title("Matchups")
with filter_column:
    week_column, refresh_column = st.columns(
        [5, 1], vertical_alignment="bottom"
    )
    with week_column:
        selected_week = st.selectbox(
            "Week",
            range(1, 19),
            index=current_week - 1,
            format_func=lambda week: f"Week {week}",
            key=f"matchup-week-v2-{stats_season}",
        )
    with refresh_column:
        force_refresh = st.button(
            "↻",
            key="refresh-matchups",
            help="Reload this week's scores and lineups from Sleeper",
            width="content",
        )
    stats_source = st.segmented_control(
        "Stat type",
        ["Actual", "Predicted"],
        default="Actual",
        width="stretch",
    )

if force_refresh:
    clear_matchup_data(
        league_id,
        selected_week,
        stats_season,
        league.season_type,
    )
    if stats_source == "Predicted":
        clear_projected_player_data(stats_season, selected_week)
    st.rerun()

# Load the selected week's lineups and resolve their team and player identities.
weekly_matchups = get_weekly_matchups(league_id, selected_week)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
players = get_nfl_players()
try:
    if stats_source == "Predicted":
        stats_by_player_id = get_projected_player_stats(
            stats_season,
            selected_week,
        )
    else:
        stats_by_player_id = get_player_stats(
            stats_season,
            league.season_type,
            selected_week,
        )
except (requests.RequestException, TypeError, ValueError):
    stats_by_player_id = {}
    source_name = (
        "ESPN projections"
        if stats_source == "Predicted"
        else "Player statistics"
    )
    st.warning(f"{source_name} could not be loaded; scores default to zero.")

try:
    nfl_schedule = get_nfl_schedule(stats_season, league.season_type)
except (requests.RequestException, TypeError, ValueError):
    nfl_schedule = []
opponents_by_team = build_week_opponents(nfl_schedule, selected_week)

st.write(f"League: {league.name}")
matchups = build_head_to_head_matchups(
    weekly_matchups.matchups,
    league,
    rosters.rosters,
    teams.users,
    players,
    stats_by_player_id,
    opponents_by_team,
)
current_user = st.session_state.get("sleeper_user")
selected_player_id = render_matchup_carousel(
    matchups,
    current_user.user_id if current_user is not None else None,
    context_key=f"{league_id}-{selected_week}-{stats_source.casefold()}",
)

if isinstance(selected_player_id, PlayerComparisonSelection):
    show_player_comparison(
        selected_player_id.left_player_id,
        selected_player_id.right_player_id,
        players,
        stats_by_player_id,
        league.scoring_settings,
        stats_source=stats_source,
        selected_week=selected_week,
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
            selected_stats=stats_by_player_id.get(str(selected_player_id), {}),
            selected_week=selected_week,
            stats_source=stats_source,
        )

stats_update = (
    get_data_update("projected_player_stats", stats_season, selected_week)
    if stats_source == "Predicted"
    else get_data_update(
        "player_stats", stats_season, league.season_type, selected_week
    )
)
render_data_disclaimer(
    get_data_update("weekly_matchups", league_id, selected_week),
    stats_update,
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
