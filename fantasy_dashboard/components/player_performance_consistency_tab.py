from typing import Any

import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_performance_graph import (
    show_performance_stat_graph,
)
from fantasy_dashboard.components.player_performance_table import render_metric_table
from fantasy_dashboard.player_performance import (
    build_consistency_statistics,
    build_consistency_trend,
    build_metric_average_values,
)


def render_consistency_tab(
    league_id: str,
    player_id: str,
    position: str,
    selected_season: str,
    selected_stat: str,
    weekly_rows: list[dict[str, Any]],
    projected_rows: list[dict[str, Any]],
    position_rows_by_player_id: dict[str, list[dict[str, Any]]],
    position_projected_rows_by_player_id: dict[str, list[dict[str, Any]]],
    position_player_ids: list[str],
    data_update: Any,
    projection_updates: list[Any],
) -> None:
    consistency_column, boom_bust_column = st.columns(2)
    with consistency_column:
        consistency_band = st.number_input(
            "Consistency band (%)",
            min_value=0.0,
            max_value=100.0,
            value=20.0,
            step=5.0,
            key=f"performance-{league_id}-{player_id}-consistency-band",
            help="Games within this percentage of the season average count.",
        )
    with boom_bust_column:
        boom_bust_tolerance = st.number_input(
            "Boom/bust tolerance",
            min_value=0.0,
            value=3.0,
            step=0.5,
            key=f"performance-{league_id}-{player_id}-boom-bust-tolerance",
            help=(
                "The amount by which actual production must beat or miss "
                "the projection."
            ),
        )
        
    consistency_statistics = build_consistency_statistics(
        weekly_rows,
        projected_rows,
        selected_stat,
        consistency_band_percent=consistency_band,
        boom_bust_tolerance=boom_bust_tolerance,
    )
    if consistency_statistics:
        consistency_statistics_by_player_id = {
            position_player_id: build_consistency_statistics(
                position_rows_by_player_id.get(position_player_id, []),
                position_projected_rows_by_player_id.get(
                    position_player_id,
                    [],
                ),
                selected_stat,
                consistency_band_percent=consistency_band,
                boom_bust_tolerance=boom_bust_tolerance,
            )
            for position_player_id in position_player_ids
        }
        consistency_position_averages = build_metric_average_values(
            consistency_statistics_by_player_id
        )
        st.caption(
            f"{selected_season} season · {len(weekly_rows)} eligible "
            "completed games"
        )
        consistency_metric_names = render_metric_table(
            consistency_statistics,
            position,
            consistency_position_averages,
            click_key="performance-consistency-graph-click",
            selection_state_key="_performance_consistency_graph_metric_key",
        )
        consistency_graph_metric_key = st.session_state.pop(
            "_performance_consistency_graph_metric_key",
            None,
        )
        if consistency_graph_metric_key in consistency_metric_names:
            show_performance_stat_graph(
                build_consistency_trend(
                    weekly_rows,
                    projected_rows,
                    selected_stat,
                    str(consistency_graph_metric_key),
                    consistency_band_percent=consistency_band,
                    boom_bust_tolerance=boom_bust_tolerance,
                ),
                selected_stat,
                consistency_metric_names[str(consistency_graph_metric_key)],
                selected_season,
            )
    else:
        st.info("No completed-game statistics are available for this player.")
    render_data_disclaimer(data_update, *projection_updates)
        
