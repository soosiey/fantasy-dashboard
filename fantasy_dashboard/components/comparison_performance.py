from collections.abc import Callable
from numbers import Real
from typing import Any

import pandas as pd
import streamlit as st

from fantasy_dashboard.components.comparison_data import (
    FULL_SEASON_WEEKS,
    ComparisonDataProvider,
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
)


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
    data_provider: ComparisonDataProvider,
) -> None:
    league_id = data_provider.league_id
    players = data_provider.players
    selected_player_ids = data_provider.selected_player_ids
    if not selected_player_ids:
        st.info("Select players from Statistics or Players to compare them here.")
        return

    season_options = data_provider.get_season_options()
    if data_provider.season_warning:
        st.warning(data_provider.season_warning)
    positions_are_compatible = data_provider.positions_are_compatible
    if not positions_are_compatible:
        st.warning(
            "You have selected players from different position groups, so only "
            "fantasy points will be compared."
        )

    relevant_stat_options = data_provider.get_stat_options()

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

    context = data_provider.get_context(selected_season, FULL_SEASON_WEEKS)
    for warning in context.warnings:
        st.warning(warning)
    league_player_ids = context.league_player_ids
    actual_rows = context.actual_rows
    projected_rows = context.projected_rows

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
        schedule = context.schedule

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
