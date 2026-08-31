from typing import Any

import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_performance_graph import (
    show_performance_stat_graph,
)
from fantasy_dashboard.components.player_performance_table import render_metric_table
from fantasy_dashboard.player_performance import (
    build_efficiency_statistics,
    build_efficiency_trend,
    build_metric_average_values,
    build_opportunity_statistics,
    build_opportunity_trend,
)


def render_opportunity_tab(position: str, selected_season: str, weekly_rows: list[dict[str, Any]], position_rows_by_player_id: dict[str, list[dict[str, Any]]], position_player_ids: list[str], data_update: Any, comparison_updates: list[Any]) -> None:
    opportunity_statistics = build_opportunity_statistics(
        weekly_rows,
        position,
    )
    if opportunity_statistics:
        opportunity_statistics_by_player_id = {
            position_player_id: build_opportunity_statistics(
                position_rows_by_player_id.get(position_player_id, []),
                position,
            )
            for position_player_id in position_player_ids
        }
        opportunity_position_averages = build_metric_average_values(
            opportunity_statistics_by_player_id
        )
        st.caption(
            f"{selected_season} season · {len(weekly_rows)} eligible "
            "completed games"
        )
        opportunity_metric_names = render_metric_table(
            opportunity_statistics,
            position,
            opportunity_position_averages,
            click_key="performance-opportunity-graph-click",
            selection_state_key="_performance_opportunity_graph_metric_key",
        )
        opportunity_graph_metric_key = st.session_state.pop(
            "_performance_opportunity_graph_metric_key",
            None,
        )
        if opportunity_graph_metric_key in opportunity_metric_names:
            opportunity_metric = next(
                row
                for row in opportunity_statistics
                if row["Key"] == opportunity_graph_metric_key
            )
            show_performance_stat_graph(
                build_opportunity_trend(
                    weekly_rows,
                    position,
                    str(opportunity_graph_metric_key),
                ),
                str(opportunity_metric["Unit"]),
                opportunity_metric_names[str(opportunity_graph_metric_key)],
                selected_season,
            )
    else:
        st.info("No opportunity statistics are available for this player.")
    render_data_disclaimer(data_update, *comparison_updates)
        


def render_efficiency_tab(position: str, selected_season: str, weekly_rows: list[dict[str, Any]], position_rows_by_player_id: dict[str, list[dict[str, Any]]], position_player_ids: list[str], data_update: Any, comparison_updates: list[Any]) -> None:
    efficiency_statistics = build_efficiency_statistics(weekly_rows, position)
    if efficiency_statistics:
        efficiency_statistics_by_player_id = {
            position_player_id: build_efficiency_statistics(
                position_rows_by_player_id.get(position_player_id, []),
                position,
            )
            for position_player_id in position_player_ids
        }
        efficiency_position_averages = build_metric_average_values(
            efficiency_statistics_by_player_id
        )
        st.caption(
            f"{selected_season} season · Efficiency is paired with its "
            "opportunity sample in the Context column"
        )
        efficiency_metric_names = render_metric_table(
            efficiency_statistics,
            position,
            efficiency_position_averages,
            click_key="performance-efficiency-graph-click",
            selection_state_key="_performance_efficiency_graph_metric_key",
        )
        efficiency_graph_metric_key = st.session_state.pop(
            "_performance_efficiency_graph_metric_key",
            None,
        )
        if efficiency_graph_metric_key in efficiency_metric_names:
            efficiency_metric = next(
                row
                for row in efficiency_statistics
                if row["Key"] == efficiency_graph_metric_key
            )
            show_performance_stat_graph(
                build_efficiency_trend(
                    weekly_rows,
                    position,
                    str(efficiency_graph_metric_key),
                ),
                str(efficiency_metric["Unit"]),
                efficiency_metric_names[str(efficiency_graph_metric_key)],
                selected_season,
            )
    else:
        st.info("No efficiency statistics are available for this player.")
    render_data_disclaimer(data_update, *comparison_updates)
        
