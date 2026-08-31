from typing import Any

import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_performance_graph import (
    show_performance_stat_graph,
)
from fantasy_dashboard.components.player_performance_table import render_metric_table
from fantasy_dashboard.data import get_data_update, get_projected_player_stats
from fantasy_dashboard.player_performance import (
    build_metric_average_values,
    build_projection_accuracy_statistics,
    build_projection_accuracy_trend,
)
from fantasy_dashboard.player_stats import build_player_stat_row


def render_projection_accuracy_tab(
    league_id: str,
    player_id: str,
    position: str,
    league: Any,
    selected_season: str,
    selected_stat: str,
    weekly_rows: list[dict[str, Any]],
    data_update: Any,
    position_rows_by_player_id: dict[str, list[dict[str, Any]]],
    position_player_ids: list[str],
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    list[Any],
]:
    hit_tolerance = st.number_input(
        "Hit tolerance",
        min_value=0.0,
        value=3.0,
        step=0.5,
        key=f"performance-{league_id}-{player_id}-hit-tolerance",
        help=(
            "A projection is a hit when it is within this many units of "
            "the actual result."
        ),
    )
    projected_rows: list[dict] = []
    position_projected_rows_by_player_id = {
        position_player_id: [] for position_player_id in position_player_ids
    }
    projection_updates = []
    try:
        for week in range(1, 19):
            projected_stats_by_player_id = get_projected_player_stats(
                selected_season,
                week,
            )
            projection_updates.append(
                get_data_update(
                    "projected_player_stats",
                    selected_season,
                    week,
                )
            )
            projected_stats = projected_stats_by_player_id.get(player_id, {})
            if projected_stats:
                projected_rows.append(
                    build_player_stat_row(
                        projected_stats,
                        league.scoring_settings,
                        week,
                        stats_available=True,
                    )
                )
            for position_player_id in position_player_ids:
                position_projected_stats = projected_stats_by_player_id.get(
                    position_player_id,
                    {},
                )
                if not position_projected_stats:
                    continue
                position_projected_rows_by_player_id[position_player_id].append(
                    build_player_stat_row(
                        position_projected_stats,
                        league.scoring_settings,
                        week,
                        stats_available=True,
                    )
                )
        if player_id in position_projected_rows_by_player_id:
            position_projected_rows_by_player_id[player_id] = projected_rows
    except (requests.RequestException, TypeError, ValueError):
        st.warning("Projected player statistics could not be loaded.")

    projection_statistics = build_projection_accuracy_statistics(
        weekly_rows,
        projected_rows,
        selected_stat,
        hit_tolerance=hit_tolerance,
    )
    if projection_statistics:
        projection_statistics_by_player_id = {
            position_player_id: build_projection_accuracy_statistics(
                position_rows_by_player_id.get(position_player_id, []),
                position_projected_rows_by_player_id.get(
                    position_player_id,
                    [],
                ),
                selected_stat,
                hit_tolerance=hit_tolerance,
            )
            for position_player_id in position_player_ids
        }
        projection_position_averages = build_metric_average_values(
            projection_statistics_by_player_id
        )
        matched_games = next(
            row["Context"]
            for row in projection_statistics
            if row["Statistic"] == "Actual average"
        )
        st.caption(f"{selected_season} season · {matched_games}")
        projection_metric_names = render_metric_table(
            projection_statistics,
            position,
            projection_position_averages,
            click_key="performance-projection-graph-click",
            selection_state_key="_performance_projection_graph_metric_key",
        )
        projection_graph_metric_key = st.session_state.pop(
            "_performance_projection_graph_metric_key",
            None,
        )
        if projection_graph_metric_key in projection_metric_names:
            show_performance_stat_graph(
                build_projection_accuracy_trend(
                    weekly_rows,
                    projected_rows,
                    selected_stat,
                    str(projection_graph_metric_key),
                    hit_tolerance=hit_tolerance,
                ),
                selected_stat,
                projection_metric_names[str(projection_graph_metric_key)],
                selected_season,
            )
    else:
        st.info(
            "No completed games have both actual and predicted data for "
            "this statistic."
        )
    render_data_disclaimer(data_update, *projection_updates)

    return projected_rows, position_projected_rows_by_player_id, projection_updates
