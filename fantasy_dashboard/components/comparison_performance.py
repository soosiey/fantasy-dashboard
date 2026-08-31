from collections.abc import Callable
from datetime import datetime
from numbers import Real
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.data import (
    get_current_nfl_season,
    get_nfl_schedule,
    get_player_stats,
    get_projected_player_stats,
    get_rosters,
)
from fantasy_dashboard.player_performance import (
    build_availability_statistics,
    build_consistency_statistics,
    build_core_performance_statistics,
    build_efficiency_statistics,
    build_metric_average_values,
    build_opportunity_statistics,
    build_projection_accuracy_statistics,
    get_team_completed_weeks,
    is_eligible_game,
)
from fantasy_dashboard.player_stats import (
    build_player_stat_row,
    get_relevant_stat_fields,
)

FLEX_POSITIONS = {"RB", "WR", "TE"}


def comparison_positions_are_compatible(positions: list[str]) -> bool:
    distinct_positions = {position.upper() for position in positions if position}
    return len(distinct_positions) <= 1 or distinct_positions <= FLEX_POSITIONS


def get_comparison_stat_options(
    players: dict[str, dict[str, Any]],
    player_ids: list[str],
) -> list[str]:
    positions = [
        str(players[player_id].get("position") or "")
        for player_id in player_ids
        if player_id in players
    ]
    if not comparison_positions_are_compatible(positions):
        return ["Fantasy Points"]

    relevant_stat_options = list(
        dict.fromkeys(
            label
            for player_id in player_ids
            if player_id in players
            for label, stat_key in get_relevant_stat_fields(
                str(players[player_id].get("position") or "")
            )
            if stat_key != "gp"
        )
    )
    if "Fantasy Points" in relevant_stat_options:
        relevant_stat_options.remove("Fantasy Points")
    relevant_stat_options.insert(0, "Fantasy Points")
    return relevant_stat_options


def make_arrow_compatible(statistics_table: pd.DataFrame) -> pd.DataFrame:
    statistics_table = statistics_table.copy()
    for column in statistics_table.columns:
        non_null_values = statistics_table[column].dropna().tolist()
        has_text = any(isinstance(value, str) for value in non_null_values)
        has_numbers = any(
            isinstance(value, Real) and not isinstance(value, bool)
            for value in non_null_values
        )
        if has_text and has_numbers:
            statistics_table[column] = statistics_table[column].map(
                lambda value: (
                    None
                    if pd.isna(value)
                    else (
                        f"{float(value):.2f}"
                        if isinstance(value, Real) and not isinstance(value, bool)
                        else str(value)
                    )
                )
            )
    return statistics_table


def get_selected_comparison_metrics(
    selected_statistics: dict[str, list[dict[str, Any]]],
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    metric_order: list[str] = []
    metric_details: dict[str, dict[str, Any]] = {}
    for statistics in selected_statistics.values():
        for metric in statistics:
            metric_key = str(metric["Key"])
            if metric_key not in metric_details:
                metric_order.append(metric_key)
                metric_details[metric_key] = metric
    return metric_order, metric_details


def _player_name(player_id: str, players: dict[str, dict[str, Any]]) -> str:
    player = players.get(player_id, {})
    name = f"{player.get('first_name') or ''} {player.get('last_name') or ''}".strip()
    position = str(player.get("position") or "—")
    return f"{name or player_id} ({position})"


def _render_comparison_metric_table(
    selected_player_ids: list[str],
    players: dict[str, dict[str, Any]],
    selected_statistics: dict[str, list[dict[str, Any]]],
    league_statistics: dict[str, list[dict[str, Any]]],
    *,
    use_symbols: bool = False,
) -> None:
    metric_order, metric_details = get_selected_comparison_metrics(selected_statistics)

    if not metric_order:
        st.info("No statistics are available for the selected players.")
        return

    table_rows = []
    player_columns: dict[str, str] = {}
    used_column_names: set[str] = set()
    for player_id in selected_player_ids:
        column_name = _player_name(player_id, players)
        if column_name in used_column_names:
            column_name = f"{column_name} · {player_id}"
        used_column_names.add(column_name)
        player_columns[player_id] = column_name

    selected_positions = list(
        dict.fromkeys(
            str(players.get(player_id, {}).get("position") or "—")
            for player_id in selected_player_ids
        )
    )
    position_averages = {
        position: build_metric_average_values(
            {
                player_id: statistics
                for player_id, statistics in league_statistics.items()
                if str(players.get(player_id, {}).get("position") or "—") == position
            }
        )
        for position in selected_positions
    }
    values_by_player = {
        player_id: {str(metric["Key"]): metric.get("Value") for metric in statistics}
        for player_id, statistics in selected_statistics.items()
    }

    for metric_key in metric_order:
        details = metric_details[metric_key]
        statistic_label = (
            details.get("Symbol") or details.get("Statistic")
            if use_symbols
            else details.get("Statistic")
        )
        row: dict[str, Any] = {"Statistic": statistic_label}
        for player_id, column_name in player_columns.items():
            row[column_name] = values_by_player.get(player_id, {}).get(metric_key)
        for position in selected_positions:
            row[f"{position} League Average"] = position_averages[position].get(
                metric_key
            )
        if "Unit" in details:
            row["Unit"] = details.get("Unit")
        table_rows.append(row)

    statistics_table = make_arrow_compatible(pd.DataFrame(table_rows))

    st.dataframe(
        statistics_table,
        column_config={
            "Statistic": st.column_config.TextColumn("Statistic", width="large"),
            "Unit": st.column_config.TextColumn("Unit", width="small"),
        },
        hide_index=True,
        width="stretch",
    )


def render_comparison_performance(
    league_id: str,
    league: Any,
    players: dict[str, dict[str, Any]],
    comparison_player_ids: list[str],
) -> None:
    selected_player_ids = [
        player_id for player_id in comparison_player_ids if player_id in players
    ]
    if not selected_player_ids:
        st.info("Select players from Statistics or Players to compare them here.")
        return

    try:
        current_season = int(get_current_nfl_season())
    except (requests.RequestException, KeyError, TypeError, ValueError):
        today = datetime.now(ZoneInfo("America/New_York")).date()
        current_season = today.year if today.month >= 3 else today.year - 1
        st.warning("The current NFL season could not be detected from Sleeper.")

    selected_positions = [
        str(players[player_id].get("position") or "")
        for player_id in selected_player_ids
    ]
    positions_are_compatible = comparison_positions_are_compatible(selected_positions)
    if not positions_are_compatible:
        st.warning(
            "You have selected players from different position groups, so only "
            "fantasy points will be compared."
        )

    season_options = [str(current_season - offset) for offset in range(3)]
    relevant_stat_options = get_comparison_stat_options(
        players,
        selected_player_ids,
    )

    year_key = f"comparison-performance-{league_id}-year"
    stat_key = f"comparison-performance-{league_id}-stat"
    if st.session_state.get(year_key) not in season_options:
        st.session_state[year_key] = season_options[0]
    if st.session_state.get(stat_key) not in relevant_stat_options:
        st.session_state[stat_key] = "Fantasy Points"

    year_column, stat_column = st.columns(2)
    with year_column:
        selected_season = st.selectbox("Year", season_options, key=year_key)
    with stat_column:
        selected_stat = st.selectbox("Stat", relevant_stat_options, key=stat_key)

    try:
        rosters = get_rosters(league_id)
        rostered_player_ids = {
            str(player_id)
            for roster in rosters.rosters
            for player_id in roster.players
            if player_id is not None and str(player_id) in players
        }
    except (requests.RequestException, TypeError, ValueError, AttributeError):
        rostered_player_ids = set(selected_player_ids)
        st.warning("League rosters could not be loaded for the league averages.")
    league_player_ids = sorted(rostered_player_ids | set(selected_player_ids))

    actual_rows = {player_id: [] for player_id in league_player_ids}
    projected_rows = {player_id: [] for player_id in league_player_ids}
    try:
        for week in range(1, 19):
            actual_stats = get_player_stats(selected_season, "regular", week)
            projected_stats = get_projected_player_stats(selected_season, week)
            for player_id in league_player_ids:
                player_actual_stats = actual_stats.get(player_id, {})
                if is_eligible_game({"stats": player_actual_stats}):
                    row = build_player_stat_row(
                        player_actual_stats,
                        league.scoring_settings,
                        week,
                        stats_available=True,
                    )
                    row["_Raw Stats"] = player_actual_stats
                    actual_rows[player_id].append(row)
                player_projected_stats = projected_stats.get(player_id, {})
                if player_projected_stats:
                    projected_rows[player_id].append(
                        build_player_stat_row(
                            player_projected_stats,
                            league.scoring_settings,
                            week,
                            stats_available=True,
                        )
                    )
    except (requests.RequestException, TypeError, ValueError):
        st.warning("Some player statistics could not be loaded.")

    performance_tab_names = [
        "Core Performance Statistics",
        "Projection Accuracy",
        "Consistency",
    ]
    if positions_are_compatible:
        performance_tab_names.extend(["Opportunity", "Efficiency"])
    performance_tab_names.append("Availability")
    performance_tabs = dict(
        zip(performance_tab_names, st.tabs(performance_tab_names), strict=True)
    )

    def render_category(
        builder: Callable[[str], list[dict[str, Any]]],
        *,
        use_symbols: bool = False,
    ) -> None:
        league_statistics = {
            player_id: builder(player_id) for player_id in league_player_ids
        }
        _render_comparison_metric_table(
            selected_player_ids,
            players,
            {
                player_id: league_statistics.get(player_id, [])
                for player_id in selected_player_ids
            },
            league_statistics,
            use_symbols=use_symbols,
        )

    with performance_tabs["Core Performance Statistics"]:
        st.caption(f"{selected_season} season · {selected_stat}")
        render_category(
            lambda player_id: build_core_performance_statistics(
                actual_rows[player_id], selected_stat
            ),
            use_symbols=True,
        )

    with performance_tabs["Projection Accuracy"]:
        hit_tolerance = st.number_input(
            "Hit tolerance",
            min_value=0.0,
            value=3.0,
            step=0.5,
            key=f"comparison-performance-{league_id}-hit-tolerance",
        )
        render_category(
            lambda player_id: build_projection_accuracy_statistics(
                actual_rows[player_id],
                projected_rows[player_id],
                selected_stat,
                hit_tolerance=hit_tolerance,
            )
        )

    with performance_tabs["Consistency"]:
        consistency_column, boom_bust_column = st.columns(2)
        with consistency_column:
            consistency_band = st.number_input(
                "Consistency band (%)",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=5.0,
                key=f"comparison-performance-{league_id}-consistency-band",
            )
        with boom_bust_column:
            boom_bust_tolerance = st.number_input(
                "Boom/bust tolerance",
                min_value=0.0,
                value=3.0,
                step=0.5,
                key=f"comparison-performance-{league_id}-boom-bust-tolerance",
            )
        render_category(
            lambda player_id: build_consistency_statistics(
                actual_rows[player_id],
                projected_rows[player_id],
                selected_stat,
                consistency_band_percent=consistency_band,
                boom_bust_tolerance=boom_bust_tolerance,
            )
        )

    if positions_are_compatible:
        with performance_tabs["Opportunity"]:
            render_category(
                lambda player_id: build_opportunity_statistics(
                    actual_rows[player_id],
                    str(players[player_id].get("position") or ""),
                )
            )

        with performance_tabs["Efficiency"]:
            render_category(
                lambda player_id: build_efficiency_statistics(
                    actual_rows[player_id],
                    str(players[player_id].get("position") or ""),
                )
            )

    with performance_tabs["Availability"]:
        try:
            schedule = get_nfl_schedule(selected_season, "regular")
        except (requests.RequestException, TypeError, ValueError):
            schedule = []
            st.warning("The completed NFL schedule could not be loaded.")

        def availability_builder(player_id: str) -> list[dict[str, Any]]:
            player = players[player_id]
            completed_weeks = get_team_completed_weeks(
                schedule,
                str(player.get("team") or ""),
            )
            statistics = build_availability_statistics(
                actual_rows[player_id],
                len(completed_weeks) if schedule else None,
                str(player.get("injury_status") or ""),
            )
            if player_id in selected_player_ids:
                for metric in statistics:
                    if metric["Key"] == "injury_status":
                        metric["Value"] = str(player.get("injury_status") or "Healthy")
            return statistics

        render_category(availability_builder)
