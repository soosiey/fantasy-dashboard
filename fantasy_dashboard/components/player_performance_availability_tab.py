from typing import Any

import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_performance_graph import (
    show_performance_stat_graph,
)
from fantasy_dashboard.components.player_performance_table import render_metric_table
from fantasy_dashboard.data import get_data_update, get_nfl_schedule
from fantasy_dashboard.player_performance import (
    build_availability_statistics,
    build_availability_trend,
    build_metric_average_values,
    get_team_completed_weeks,
)


def render_availability_tab(
    players: dict[str, dict[str, Any]],
    player: dict[str, Any],
    position: str,
    team: str,
    selected_season: str,
    weekly_rows: list[dict[str, Any]],
    position_rows_by_player_id: dict[str, list[dict[str, Any]]],
    position_player_ids: list[str],
    data_update: Any,
    comparison_updates: list[Any],
) -> None:
    schedule = []
    schedule_update = None
    try:
        schedule = get_nfl_schedule(selected_season, "regular")
        schedule_update = get_data_update(
            "nfl_schedule",
            selected_season,
            "regular",
        )
    except (requests.RequestException, TypeError, ValueError):
        st.warning("The completed NFL schedule could not be loaded.")
        
    completed_team_weeks = get_team_completed_weeks(schedule, team)
    team_completed_games = len(completed_team_weeks) if schedule else None
    availability_statistics = build_availability_statistics(
        weekly_rows,
        team_completed_games,
        str(player.get("injury_status") or ""),
    )
    availability_statistics_by_player_id = {}
    for position_player_id in position_player_ids:
        position_player = players.get(position_player_id, {})
        position_team_weeks = get_team_completed_weeks(
            schedule,
            str(position_player.get("team") or ""),
        )
        availability_statistics_by_player_id[position_player_id] = (
            build_availability_statistics(
                position_rows_by_player_id.get(position_player_id, []),
                len(position_team_weeks) if schedule else None,
                str(position_player.get("injury_status") or ""),
            )
        )
    availability_position_averages = build_metric_average_values(
        availability_statistics_by_player_id
    )
    st.caption(
        f"{selected_season} season · Bye weeks are excluded from games missed"
    )
    availability_metric_names = render_metric_table(
        availability_statistics,
        position,
        availability_position_averages,
        click_key="performance-availability-graph-click",
        selection_state_key="_performance_availability_graph_metric_key",
    )
    availability_graph_metric_key = st.session_state.pop(
        "_performance_availability_graph_metric_key",
        None,
    )
    if availability_graph_metric_key in availability_metric_names:
        availability_metric = next(
            row
            for row in availability_statistics
            if row["Key"] == availability_graph_metric_key
        )
        show_performance_stat_graph(
            build_availability_trend(
                weekly_rows,
                completed_team_weeks,
                str(player.get("injury_status") or ""),
                str(availability_graph_metric_key),
            ),
            str(availability_metric["Unit"]),
            availability_metric_names[str(availability_graph_metric_key)],
            selected_season,
        )
    render_data_disclaimer(
        data_update,
        schedule_update,
        *comparison_updates,
    )
