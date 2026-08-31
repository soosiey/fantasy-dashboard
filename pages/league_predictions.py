from math import ceil, log2

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.comparison_selection import render_comparison_sidebar
from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.matchup_board import (
    PlayerComparisonSelection,
    render_matchup_carousel,
)
from fantasy_dashboard.components.player_comparison import show_player_comparison
from fantasy_dashboard.components.player_details import show_player_details
from fantasy_dashboard.components.playoff_bracket import render_playoff_bracket
from fantasy_dashboard.data import (
    get_data_update,
    get_default_nfl_week,
    get_league,
    get_league_users,
    get_nfl_players,
    get_nfl_schedule,
    get_projected_player_stats,
    get_rosters,
    get_weekly_matchup_schedules,
)
from fantasy_dashboard.league_predictions import (
    build_optimized_week_matchups,
    project_playoffs,
    project_regular_season,
)
from fantasy_dashboard.matchups import (
    build_head_to_head_matchups,
    build_week_game_statuses,
    build_week_opponents,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    require_authentication,
    resolve_league_id,
)

require_authentication("league-predictions")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

if not st.session_state.get(ANALYSIS_MODE_KEY):
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 95rem; }</style>",
    unsafe_allow_html=True,
)
st.title("League Predictions")

league = get_league(league_id)
rosters = get_rosters(league_id)
teams = get_league_users(league_id)
players = get_nfl_players()
try:
    current_week = get_default_nfl_week(league.season)
except (requests.RequestException, KeyError, TypeError, ValueError):
    current_week = 1

regular_season_end = max(1, league.settings.playoff_start_week - 1)
playoff_team_count = min(league.settings.playoff_teams, len(rosters.rosters))
playoff_round_count = (
    ceil(log2(playoff_team_count)) if playoff_team_count >= 2 else 0
)
last_projection_week = min(
    18,
    league.settings.playoff_start_week + playoff_round_count - 1,
)
projection_start_week = (
    current_week
    if current_week <= regular_season_end
    else league.settings.playoff_start_week
)
projection_weeks = range(
    projection_start_week,
    last_projection_week + 1,
)

projections_by_week = {}
unavailable_projection_weeks = []
for week in projection_weeks:
    try:
        projections_by_week[week] = get_projected_player_stats(league.season, week)
        if not projections_by_week[week]:
            unavailable_projection_weeks.append(week)
    except (OSError, requests.RequestException, TypeError, ValueError):
        projections_by_week[week] = {}
        unavailable_projection_weeks.append(week)

matchups_by_week = {}
unavailable_matchup_weeks = []
if current_week <= regular_season_end:
    matchup_schedules, unavailable_matchup_weeks = get_weekly_matchup_schedules(
        league_id,
        current_week,
        regular_season_end,
    )
    for week, weekly_matchups in matchup_schedules.items():
        if weekly_matchups.matchups:
            matchups_by_week[week] = weekly_matchups.matchups
        else:
            unavailable_matchup_weeks.append(week)

try:
    nfl_schedule = get_nfl_schedule(league.season, league.season_type)
except (requests.RequestException, TypeError, ValueError):
    nfl_schedule = []

standings = project_regular_season(
    league,
    rosters.rosters,
    teams.users,
    players,
    matchups_by_week,
    projections_by_week,
)
playoff_projection = project_playoffs(
    league,
    rosters.rosters,
    standings,
    players,
    projections_by_week,
)

st.write(f"League: {league.name}")
if current_week <= regular_season_end:
    st.caption(
        f"Current Sleeper records plus optimized projected lineups from Week "
        f"{current_week} through Week {regular_season_end}."
    )
else:
    st.caption("Regular-season rankings use the current final Sleeper records.")

if unavailable_matchup_weeks:
    weeks = ", ".join(str(week) for week in unavailable_matchup_weeks)
    st.warning(
        f"Sleeper did not provide scheduled league matchups for Week(s) {weeks}; "
        "those weeks are not included in the final record."
    )
if unavailable_projection_weeks:
    weeks = ", ".join(str(week) for week in unavailable_projection_weeks)
    st.warning(
        f"ESPN projections were unavailable for Week(s) {weeks}; those optimized "
        "scores are treated as zero."
    )

st.header("Predicted Final Rankings")
standings_table = pd.DataFrame(
    [
        {
            "Seed": standing.seed,
            "Team": standing.team_name,
            "Projected Record": (
                f"{standing.wins}-{standing.losses}-{standing.ties}"
            ),
            "Projected PF": standing.points_for,
            "Projected PA": standing.points_against,
            "Tournament": (
                "Playoffs" if standing.seed <= playoff_team_count else "Out"
            ),
        }
        for standing in standings
    ]
)
st.dataframe(
    standings_table,
    hide_index=True,
    width="stretch",
    column_config={
        "Seed": st.column_config.NumberColumn(width="small"),
        "Team": st.column_config.TextColumn(width="large"),
        "Projected Record": st.column_config.TextColumn(width="medium"),
        "Projected PF": st.column_config.NumberColumn(format="%.2f"),
        "Projected PA": st.column_config.NumberColumn(format="%.2f"),
        "Tournament": st.column_config.TextColumn(width="small"),
    },
)

st.header("Best Possible Weekly Matchups")
prediction_week_options = list(range(current_week, regular_season_end + 1))
if prediction_week_options:
    prediction_week_key = f"league-prediction-week-{league_id}-{league.season}"
    if st.session_state.get(prediction_week_key) not in prediction_week_options:
        st.session_state[prediction_week_key] = prediction_week_options[0]
    selected_prediction_week = st.selectbox(
        "Week",
        prediction_week_options,
        format_func=lambda week: f"Week {week}",
        key=prediction_week_key,
    )
    selected_projections = projections_by_week.get(selected_prediction_week, {})
    optimized_week_matchups = build_optimized_week_matchups(
        league,
        rosters.rosters,
        players,
        matchups_by_week.get(selected_prediction_week, []),
        selected_projections,
    )
    predicted_matchups = build_head_to_head_matchups(
        optimized_week_matchups,
        league,
        rosters.rosters,
        teams.users,
        players,
        selected_projections,
        build_week_opponents(nfl_schedule, selected_prediction_week),
        build_week_game_statuses(nfl_schedule, selected_prediction_week),
    )
    current_user = st.session_state.get("sleeper_user")
    selected_player_id = render_matchup_carousel(
        predicted_matchups,
        current_user.user_id if current_user is not None else None,
        context_key=(
            f"league-prediction-{league_id}-{selected_prediction_week}"
        ),
    )

    if isinstance(selected_player_id, PlayerComparisonSelection):
        show_player_comparison(
            selected_player_id.left_player_id,
            selected_player_id.right_player_id,
            players,
            selected_projections,
            league.scoring_settings,
            stats_source="Predicted",
            selected_week=selected_prediction_week,
        )
    elif selected_player_id:
        selected_player = players.get(str(selected_player_id))
        if selected_player is not None:
            show_player_details(
                str(selected_player_id),
                selected_player,
                league.season,
                league.season_type,
                league.scoring_settings,
                selected_stats=selected_projections.get(
                    str(selected_player_id), {}
                ),
                selected_week=selected_prediction_week,
                stats_source="Predicted",
                show_stat_filter=True,
            )
else:
    st.info("There are no remaining regular-season matchups to project.")

st.header("Projected Playoff Tournament")
if playoff_projection.champion is not None:
    champion_column, runner_up_column = st.columns(2)
    champion_column.metric("Projected Champion", playoff_projection.champion.team_name)
    runner_up_column.metric(
        "Projected Runner-up",
        (
            playoff_projection.runner_up.team_name
            if playoff_projection.runner_up is not None
            else "—"
        ),
    )
render_playoff_bracket(playoff_projection.rounds)

with st.expander("How this prediction works"):
    st.markdown(
        """
        - Each team's current roster is frozen for the rest of the season.
        - Every week uses the highest-scoring legal lineup from ESPN's player
          projections and this league's scoring settings.
        - Current Sleeper wins, losses, ties, and points are retained; only
          remaining scheduled head-to-head matchups are added.
        - The playoff view uses a standard fixed single-elimination bracket with
          byes for the highest seeds. Exact score ties advance the higher seed.
        - Trades, waiver moves, injuries after the projection update, league-median
          games, playoff reseeding, and multi-week playoff rounds are not modeled.
        """
    )

render_comparison_sidebar(players, league_id)
render_data_disclaimer(
    get_data_update("rosters", league_id),
    get_data_update("nfl_schedule", league.season, league.season_type),
    *(
        get_data_update("projected_player_stats", league.season, week)
        for week in projection_weeks
    ),
)

with st.bottom:
    back_to_overview = st.button("Back to Overview")

if back_to_overview:
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.switch_page(
        "pages/overview.py",
        query_params={"league_id": league_id},
    )
