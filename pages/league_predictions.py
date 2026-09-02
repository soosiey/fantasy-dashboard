from contextlib import ExitStack
from math import ceil, log2

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.comparison_selection import render_comparison_sidebar
from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.draft_grades import (
    render_draft_grade_cards,
    render_overall_draft_grade_cards,
)
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
    get_draft_picks,
    get_league,
    get_league_users,
    get_nfl_players,
    get_nfl_schedule,
    get_projected_player_stats,
    get_rosters,
    get_weekly_matchup_schedules,
)
from fantasy_dashboard.draft_grading import DraftGradeWeights, grade_draft_picks
from fantasy_dashboard.league_predictions import (
    build_optimized_week_matchups,
    project_draft_championship_odds,
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
st.info(
    "Draft grades assess each roster as it was originally drafted. Season "
    "predictions use the current roster, record, schedule, and projection state, "
    "so the two outlooks may differ."
)

draft_grades_tab, season_predictions_tab = st.tabs(
    ["Draft Grades", "Season Predictions"]
)
with draft_grades_tab:
    draft_grade_league = get_league(league_id)
    draft_id = draft_grade_league.draft_id if draft_grade_league is not None else ""
    if not draft_id or draft_id == "None":
        st.info("This league does not have a draft associated with it.")
    else:
        try:
            draft_grade_picks = get_draft_picks(draft_id)
            draft_grade_teams = get_league_users(league_id)
        except (requests.RequestException, TypeError, ValueError) as error:
            st.warning(f"Draft grades could not be loaded: {error}")
        else:
            draft_grade_players = get_nfl_players()
            draft_grade_team_list = (
                draft_grade_teams.users if draft_grade_teams is not None else []
            )
            try:
                draft_grade_projections = get_projected_player_stats(
                    draft_grade_league.season, None
                )
            except (OSError, requests.RequestException, TypeError, ValueError):
                draft_grade_projections = {}
                st.warning(
                    "Season projections could not be loaded; unavailable players "
                    "will receive zero projected value."
                )

            is_auction_draft = any(
                pick.amount is not None for pick in draft_grade_picks.picks
            )
            with st.expander("Pick score weights"):
                score_columns = st.columns(3 if is_auction_draft else 2)
                strength_column, fit_column = score_columns[:2]
                with strength_column:
                    strength_weight = st.slider(
                        "Positional strength",
                        0,
                        100,
                        30 if is_auction_draft else 40,
                        key=f"draft-grade-strength-weight-{league_id}",
                    )
                with fit_column:
                    roster_fit_weight = st.slider(
                        "Roster value",
                        0,
                        100,
                        45 if is_auction_draft else 60,
                        key=f"draft-grade-roster-weight-{league_id}",
                    )
                cost_weight = 0
                if is_auction_draft:
                    with score_columns[2]:
                        cost_weight = st.slider(
                            "Cost efficiency",
                            0,
                            100,
                            25,
                            key=f"draft-grade-cost-weight-{league_id}",
                        )
                depth_column, wait_column = st.columns(2)
                with depth_column:
                    bench_depth_weight = st.slider(
                        "Bench depth importance",
                        0.0,
                        1.0,
                        0.10,
                        0.05,
                        key=f"draft-grade-depth-weight-{league_id}",
                    )
                with wait_column:
                    wait_cost_weight = st.slider(
                        "Position tier-drop importance",
                        0.0,
                        1.0,
                        0.05,
                        0.05,
                        key=f"draft-grade-wait-weight-{league_id}",
                    )
                st.caption(
                    "The primary score metrics are normalized to their combined "
                    "weight. Advanced weights tune depth and the cost of waiting "
                    "until the owner's next selection."
                )
                st.markdown("""
                    **Model:** Strength is the player's empirical percentile within
                    their position. Roster value is the pick's marginal
                    value-over-replacement, including diminishing bench depth and
                    realized positional tier drop, divided by the best feasible
                    player available at that pick. A feasibility constraint reserves
                    enough future selections to fill every required starting slot.
                    For auction drafts, cost efficiency compares the winning bid to
                    a fair value recalculated from the players, roster spots, and
                    realized dollars remaining immediately before that bid. **Bench
                    depth importance** controls how much above-replacement value from
                    non-starters contributes to roster value; higher settings reward
                    depth more, while lower settings prioritize the starting lineup.
                    **Position tier-drop importance** controls how strongly a pick is
                    rewarded for avoiding the projected drop at that position before
                    the owner's next selection; higher settings make the cost of
                    waiting more influential.
                    """)

            draft_grade_weights = DraftGradeWeights(
                strength=float(strength_weight),
                roster_fit=float(roster_fit_weight),
                cost=float(cost_weight),
                bench_depth=float(bench_depth_weight),
                wait_cost=float(wait_cost_weight),
            )
            draft_pick_grades = grade_draft_picks(
                draft_grade_league,
                draft_grade_picks.picks,
                draft_grade_players,
                draft_grade_projections,
                draft_grade_weights,
            )
            draft_team_projections = project_draft_championship_odds(
                draft_grade_league,
                draft_grade_picks.picks,
                draft_grade_team_list,
                draft_grade_players,
                draft_grade_projections,
            )
            per_pick_tab, overall_tab = st.tabs(["Per Pick", "Overall"])
            with per_pick_tab:
                team_names_by_user_id = {
                    team.user_id: team.display_team_name
                    for team in draft_grade_team_list
                }
                selected_draft_team = st.selectbox(
                    "Team",
                    ["", *team_names_by_user_id],
                    index=0,
                    format_func=lambda user_id: (
                        "Everyone"
                        if not user_id
                        else team_names_by_user_id.get(user_id, "Unknown Team")
                    ),
                    key=f"draft-grade-team-filter-{league_id}",
                )
                filtered_draft_picks = [
                    pick
                    for pick in draft_grade_picks.picks
                    if not selected_draft_team or pick.picked_by == selected_draft_team
                ]
                render_draft_grade_cards(
                    filtered_draft_picks,
                    draft_grade_players,
                    draft_grade_team_list,
                    league_id,
                    draft_pick_grades,
                )
            with overall_tab:
                st.caption(
                    "Overall grades come from 5,000 simulated seasons using each "
                    "drafted roster's best projected legal lineup. The favorite is "
                    "not automatically assigned 100: an equal-share championship "
                    "chance is graded as 75, and nearby title odds receive nearby "
                    "scores. Raw probabilities are shown inside each card."
                )
                render_overall_draft_grade_cards(
                    draft_grade_picks.picks,
                    draft_grade_players,
                    draft_grade_team_list,
                    league_id,
                    draft_team_projections,
                )
            render_data_disclaimer(
                get_data_update("draft_picks", draft_id),
                get_data_update(
                    "projected_player_stats", draft_grade_league.season, None
                ),
            )

season_tab_context = ExitStack()
season_tab_context.enter_context(season_predictions_tab)

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
playoff_round_count = ceil(log2(playoff_team_count)) if playoff_team_count >= 2 else 0
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
            "Projected Record": (f"{standing.wins}-{standing.losses}-{standing.ties}"),
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
        context_key=(f"league-prediction-{league_id}-{selected_prediction_week}"),
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
                selected_stats=selected_projections.get(str(selected_player_id), {}),
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
    st.markdown("""
        - Each team's current roster is frozen for the rest of the season.
        - Every week uses the highest-scoring legal lineup from ESPN's player
          projections and this league's scoring settings.
        - Current Sleeper wins, losses, ties, and points are retained; only
          remaining scheduled head-to-head matchups are added.
        - The playoff view uses a standard fixed single-elimination bracket with
          byes for the highest seeds. Exact score ties advance the higher seed.
        - Trades, waiver moves, injuries after the projection update, league-median
          games, playoff reseeding, and multi-week playoff rounds are not modeled.
        """)

render_comparison_sidebar(players, league_id)
render_data_disclaimer(
    get_data_update("rosters", league_id),
    get_data_update("nfl_schedule", league.season, league.season_type),
    *(
        get_data_update("projected_player_stats", league.season, week)
        for week in projection_weeks
    ),
)
season_tab_context.close()

with st.bottom:
    back_to_overview = st.button("Back to Overview")

if back_to_overview:
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.switch_page(
        "pages/overview.py",
        query_params={"league_id": league_id},
    )
