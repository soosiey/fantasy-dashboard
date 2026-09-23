import pandas as pd
import streamlit as st

from fantasy_dashboard.backtesting import (
    aggregate_weekly_stats,
    load_completed_snapshot_weeks,
)
from fantasy_dashboard.data import (
    get_league,
    get_league_users,
    get_nfl_players,
    get_rosters,
)
from fantasy_dashboard.player_regression import RegressionPrediction
from fantasy_dashboard.player_stats import (
    ALL_STATS,
    UPDATED_PROJECTED_STATS_LABEL,
    build_player_identity_image,
    build_player_roster_labels,
    build_player_stat_rows,
    calculate_fantasy_points,
    get_relevant_stat_labels,
    get_rosterable_positions,
)
from fantasy_dashboard.regression_cache import (
    load_or_create_regression_artifact,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    require_authentication,
    resolve_league_id,
    sync_query_params,
)


def _fantasy_points_by_player(
    stats_by_player: dict[str, dict], scoring_settings: dict
) -> dict[str, float]:
    return {
        player_id: calculate_fantasy_points(stats, scoring_settings)
        for player_id, stats in stats_by_player.items()
    }


require_authentication("backtesting")
league_id = resolve_league_id()
if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")
if not st.session_state.get(ANALYSIS_MODE_KEY):
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.rerun()

st.markdown(
    "<style>[data-testid='stMainBlockContainer'] { max-width: 105rem; }</style>",
    unsafe_allow_html=True,
)
st.title("Backtesting")
st.caption(
    "Compare completed results with the ESPN projections captured before kickoff "
    "and with chronological ridge-regression adjustments."
)

league = get_league(league_id)
season = int(league.season)
snapshot_weeks = load_completed_snapshot_weeks(league_id, season)

if not snapshot_weeks:
    st.info(
        "No completed projection/actual snapshot pairs are available for this "
        "league and season."
    )
else:
    players = get_nfl_players()
    rosters = get_rosters(league_id)
    teams = get_league_users(league_id)
    roster_labels = build_player_roster_labels(rosters.rosters, teams.users)
    rosterable_positions = get_rosterable_positions(league.roster_positions)
    completed_weeks = sorted(snapshot_weeks)

    requested_position = str(st.query_params.get("position") or "")
    requested_team = str(st.query_params.get("team") or "")
    requested_availability = str(st.query_params.get("availability") or "").casefold()
    requested_period = str(st.query_params.get("period") or "week").casefold()
    try:
        requested_week = int(st.query_params.get("week") or completed_weeks[-1])
    except (TypeError, ValueError):
        requested_week = completed_weeks[-1]
    if requested_week not in snapshot_weeks:
        requested_week = completed_weeks[-1]

    prefix = f"backtesting-{league_id}-{season}"
    position_options = ["All Positions", "FLEX", *rosterable_positions]
    all_teams_label = "All available teams"
    team_options = [
        all_teams_label,
        *sorted(
            {
                str(player.get("team"))
                for player in players.values()
                if player.get("active") and player.get("team")
            }
        ),
    ]
    defaults = {
        f"{prefix}-available": requested_availability == "available",
        f"{prefix}-team": (
            requested_team if requested_team in team_options else all_teams_label
        ),
        f"{prefix}-position": (
            requested_position
            if requested_position in position_options
            else "All Positions"
        ),
        f"{prefix}-period": "Season" if requested_period == "season" else "Week",
        f"{prefix}-week": requested_week,
        f"{prefix}-search": str(st.query_params.get("search") or ""),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    (
        availability_column,
        team_column,
        position_column,
        period_column,
        week_column,
    ) = st.columns(5)
    with availability_column:
        available_only = st.toggle("Available players only", key=f"{prefix}-available")
    with team_column:
        selected_team = st.selectbox(
            "NFL team",
            team_options,
            key=f"{prefix}-team",
        )
    with position_column:
        selected_position_label = st.selectbox(
            "Position", position_options, key=f"{prefix}-position"
        )
    with period_column:
        stats_period = (
            st.segmented_control(
                "Period",
                ["Season", "Week"],
                key=f"{prefix}-period",
                width="stretch",
            )
            or "Week"
        )
    with week_column:
        selected_week = (
            st.selectbox(
                "Week",
                completed_weeks,
                format_func=lambda week: f"Week {week}",
                key=f"{prefix}-week",
            )
            if stats_period == "Week"
            else None
        )
    player_search = st.text_input(
        "Player name",
        placeholder="Search by player name",
        key=f"{prefix}-search",
    )

    sync_query_params(
        league_id=league_id,
        availability="available" if available_only else None,
        team=selected_team if selected_team != all_teams_label else None,
        position=(
            selected_position_label
            if selected_position_label != "All Positions"
            else None
        ),
        period=stats_period.casefold(),
        week=selected_week,
        stats=None,
        search=player_search.strip() or None,
    )

    with st.spinner("Loading cached regression backtest..."):
        regression_artifact = load_or_create_regression_artifact(
            league_id,
            season,
            players,
            league.scoring_settings,
            snapshot_weeks,
        )
    predictions = (
        regression_artifact.backtest_predictions if regression_artifact else ()
    )
    best_adjustment_weight = (
        regression_artifact.best_adjustment_weight if regression_artifact else 1.0
    )
    requested_weight = st.query_params.get("weight")
    try:
        requested_weight_percent = int(requested_weight)
    except (TypeError, ValueError):
        requested_weight_percent = round(best_adjustment_weight * 100)
    requested_weight_percent = min(max(requested_weight_percent, 0), 100)
    weight_key = f"{prefix}-adjustment-weight"
    if weight_key not in st.session_state:
        st.session_state[weight_key] = requested_weight_percent
    adjustment_weight_percent = st.slider(
        "Regression adjustment weight",
        0,
        100,
        key=weight_key,
        help=(
            "0% keeps the original ESPN projection; 100% applies the full ridge "
            "residual adjustment."
        ),
    )
    adjustment_weight = adjustment_weight_percent / 100
    st.caption(
        f"The default {best_adjustment_weight:.0%} weight minimizes MAE in the "
        "chronological 2025 backtest."
    )
    sync_query_params(weight=str(adjustment_weight_percent))
    prediction_weeks = (
        set(completed_weeks) if selected_week is None else {selected_week}
    )
    predictions_by_player: dict[str, list[RegressionPrediction]] = {}
    for prediction in predictions:
        if prediction.week in prediction_weeks:
            predictions_by_player.setdefault(prediction.player_id, []).append(
                prediction
            )

    actual_stats = aggregate_weekly_stats(snapshot_weeks, "actual", selected_week)
    projection_stats = aggregate_weekly_stats(
        snapshot_weeks, "projection", selected_week
    )
    actual_points = _fantasy_points_by_player(actual_stats, league.scoring_settings)
    projected_points = _fantasy_points_by_player(
        projection_stats, league.scoring_settings
    )
    adjusted_points = {
        player_id: sum(
            max(
                0.0,
                row.provider_projection + adjustment_weight * row.predicted_adjustment,
            )
            for row in rows
        )
        for player_id, rows in predictions_by_player.items()
    }

    selected_position = (
        None if selected_position_label == "All Positions" else selected_position_label
    )
    player_rows = build_player_stat_rows(
        players,
        rosters.rosters,
        actual_stats,
        league.scoring_settings,
        rosterable_positions,
        selected_position=selected_position,
        available_only=available_only,
        roster_labels_by_player_id=roster_labels,
    )
    if selected_team != all_teams_label:
        player_rows = [row for row in player_rows if row["Team"] == selected_team]
    search_query = player_search.strip().casefold()
    if search_query:
        player_rows = [
            row for row in player_rows if search_query in str(row["Player"]).casefold()
        ]

    comparison_rows = []
    for row in player_rows:
        player_id = str(row["Player ID"])
        actual = actual_points.get(player_id)
        projected = projected_points.get(player_id)
        adjusted = adjusted_points.get(player_id)
        comparison_rows.append(
            {
                **row,
                "Actual FP": actual,
                "Then-Projected FP": projected,
                "Adjustment": (
                    adjusted - projected
                    if adjusted is not None and projected is not None
                    else None
                ),
                UPDATED_PROJECTED_STATS_LABEL: adjusted,
                "Original Error": (
                    actual - projected
                    if actual is not None and projected is not None
                    else None
                ),
                "Adjusted Error": (
                    actual - adjusted
                    if actual is not None and adjusted is not None
                    else None
                ),
            }
        )

    period_label = (
        f"Week {selected_week}" if selected_week is not None else "completed season"
    )
    st.caption(
        f"{len(comparison_rows):,} players · {period_label} · Raw stat columns show "
        "actual results. Adjustments use only information available before each "
        "selected week."
    )
    if regression_artifact and regression_artifact.unavailable_historical_inputs:
        st.warning(
            f"{regression_artifact.unavailable_historical_inputs} historical regression "
            "inputs were unavailable; adjustments use the remaining cached history."
        )
    if not comparison_rows:
        st.info("No players match the selected filters.")
    else:
        table = pd.DataFrame(comparison_rows).drop(columns="Fantasy Points")
        table["Player"] = [
            build_player_identity_image(player, owner)
            for player, owner in zip(table["Player"], table["Roster"])
        ]
        table = table.drop(columns="Roster")
        summary_columns = [
            "Actual FP",
            "Then-Projected FP",
            "Adjustment",
            UPDATED_PROJECTED_STATS_LABEL,
            "Original Error",
            "Adjusted Error",
        ]
        identity_columns = [
            "Player ID",
            "Player",
            "Position",
            "Team",
            "Availability",
        ]
        stat_columns = [label for label, _ in ALL_STATS]
        table = table[[*identity_columns, *summary_columns, *stat_columns]]
        table = table.sort_values(
            ["Actual FP", "Player"], ascending=[False, True], na_position="last"
        )

        def highlight_relevant_stats(row: pd.Series) -> list[str]:
            relevant = get_relevant_stat_labels(str(row["Position"]))
            return [
                "background-color: rgba(59, 130, 246, 0.10)"
                if column in relevant
                else ""
                for column in row.index
            ]

        st.dataframe(
            table.style.apply(highlight_relevant_stats, axis=1),
            hide_index=True,
            height=700,
            width="stretch",
            column_config={
                "Player ID": None,
                "Player": st.column_config.ImageColumn("Player", width=260),
                "Position": st.column_config.TextColumn("Pos", width="small"),
                "Team": st.column_config.TextColumn(width="medium"),
                "Availability": st.column_config.TextColumn(width="medium"),
                **{
                    column: st.column_config.NumberColumn(format="%.2f", width="medium")
                    for column in [*summary_columns, *stat_columns]
                },
            },
        )

    with st.expander("How adjusted projections are backtested"):
        st.markdown(
            "The ridge model predicts the residual between actual fantasy points and "
            "the saved pre-kickoff ESPN projection. Week 1 uses 2024–2025 history. "
            "Each later week additionally uses all completed weeks from this season. "
            "A player's current-week result is never included in its own adjustment. "
            "The displayed forecast is max(0, ESPN projection + slider weight × "
            "predicted residual). The adjustment applies to fantasy points; the raw "
            "stat columns remain the captured actual values."
        )
