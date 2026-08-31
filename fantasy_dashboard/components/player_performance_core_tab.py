from typing import Any

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_performance_graph import (
    open_performance_stat_graph,
    show_performance_stat_graph,
)
from fantasy_dashboard.data import (
    get_data_update,
    get_player_stats,
    get_player_weekly_stats,
    get_rosters,
)
from fantasy_dashboard.graph_stats import build_actual_weekly_stat_rows
from fantasy_dashboard.player_performance import (
    build_core_performance_statistics,
    build_core_performance_trend,
    build_position_average_statistics,
    is_eligible_game,
)
from fantasy_dashboard.player_stats import build_player_stat_row


def render_core_performance_tab(
    league_id: str,
    player_id: str,
    players: dict[str, dict[str, Any]],
    position: str,
    league: Any,
    selected_season: str,
    selected_stat: str,
) -> tuple[
    list[dict[str, Any]],
    Any,
    list[Any],
    dict[str, list[dict[str, Any]]],
    list[str],
]:
    weekly_rows: list[dict[str, Any]] = []
    data_update = None
    comparison_updates: list[Any] = []
    position_rows_by_player_id: dict[str, list[dict[str, Any]]] = {}
    position_player_ids: list[str] = []
    try:
        weekly_stats = get_player_weekly_stats(
            player_id,
            selected_season,
            "regular",
        )
        eligible_weekly_stats = {
            week: record
            for week, record in weekly_stats.items()
            if is_eligible_game(record)
        }
        weekly_rows = build_actual_weekly_stat_rows(
            eligible_weekly_stats,
            league.scoring_settings,
        )
        for weekly_row in weekly_rows:
            record = eligible_weekly_stats.get(int(weekly_row["Week"]), {})
            weekly_row["_Raw Stats"] = record.get("stats", {})
        data_update = get_data_update(
            "player_weekly_stats",
            player_id,
            selected_season,
            "regular",
        )
    except (requests.RequestException, TypeError, ValueError):
        st.warning("Actual player statistics could not be loaded.")

    statistics = build_core_performance_statistics(weekly_rows, selected_stat)
    if statistics:
        try:
            rosters = get_rosters(league_id)
            if rosters is None:
                raise ValueError("League rosters are unavailable.")
            rostered_player_ids = {
                str(rostered_player_id)
                for roster in rosters.rosters
                for rostered_player_id in roster.players
                if rostered_player_id is not None
            }
            position_player_ids = sorted(
                rostered_player_id
                for rostered_player_id in rostered_player_ids
                if str(players.get(rostered_player_id, {}).get("position") or "")
                == position
            )
            position_rows_by_player_id = {
                rostered_player_id: [] for rostered_player_id in position_player_ids
            }
            for week in range(1, 19):
                stats_by_player_id = get_player_stats(
                    selected_season,
                    "regular",
                    week,
                )
                comparison_updates.append(
                    get_data_update(
                        "player_stats",
                        selected_season,
                        "regular",
                        week,
                    )
                )
                for position_player_id in position_player_ids:
                    player_week_stats = stats_by_player_id.get(
                        position_player_id,
                        {},
                    )
                    record = {"stats": player_week_stats}
                    if not is_eligible_game(record):
                        continue
                    position_weekly_row = build_player_stat_row(
                        player_week_stats,
                        league.scoring_settings,
                        week,
                        stats_available=True,
                    )
                    position_weekly_row["_Raw Stats"] = player_week_stats
                    position_rows_by_player_id[position_player_id].append(
                        position_weekly_row
                    )
            if player_id in position_rows_by_player_id:
                position_rows_by_player_id[player_id] = weekly_rows
        except (requests.RequestException, TypeError, ValueError):
            position_rows_by_player_id = {}
            st.warning("The positional league average could not be loaded.")

        position_averages = build_position_average_statistics(
            position_rows_by_player_id,
            selected_stat,
        )
        st.caption(
            f"{selected_season} season · "
            f"{len(weekly_rows)} eligible completed games · "
            f"League average across "
            f"{sum(bool(rows) for rows in position_rows_by_player_id.values())} "
            f"rostered {position} players"
        )
        statistics_table = pd.DataFrame(statistics)
        metric_keys = statistics_table["Key"].astype(str).tolist()
        metric_names_by_key = {
            str(row["Key"]): str(row["Statistic"]) for row in statistics
        }
        statistics_table["Statistic"] = statistics_table["Symbol"]
        league_average_column = f"{position} League Average"
        difference_column = f"vs {position} Average"
        statistics_table[league_average_column] = [
            position_averages.get(metric_key) for metric_key in metric_keys
        ]
        statistics_table[difference_column] = [
            (
                float(value) - position_averages[metric_key]
                if metric_key in position_averages and pd.notna(value)
                else None
            )
            for metric_key, value in zip(
                metric_keys,
                statistics_table["Value"],
            )
        ]
        statistics_table = statistics_table[
            [
                "Statistic",
                "Value",
                league_average_column,
                difference_column,
                "Context",
            ]
        ].copy()
        statistics_table["View Graph"] = "View"
        st.dataframe(
            statistics_table,
            column_config={
                "Statistic": st.column_config.TextColumn(
                    "Statistic",
                    width="large",
                ),
                "Value": st.column_config.NumberColumn(
                    selected_stat,
                    format="%.2f",
                    width="small",
                ),
                league_average_column: st.column_config.NumberColumn(
                    league_average_column,
                    format="%.2f",
                    width="small",
                ),
                difference_column: st.column_config.NumberColumn(
                    difference_column,
                    format="%.2f",
                    width="small",
                ),
                "Context": st.column_config.TextColumn(
                    "Context",
                    width="medium",
                ),
                "View Graph": st.column_config.ButtonColumn(
                    "View Graph",
                    width="small",
                    type="secondary",
                    on_click=open_performance_stat_graph,
                    args=(
                        "performance-core-graph-click",
                        metric_keys,
                        "_performance_core_graph_metric_key",
                    ),
                    key="performance-core-graph-click",
                ),
            },
            hide_index=True,
            width="stretch",
        )

        graph_metric_key = st.session_state.pop(
            "_performance_core_graph_metric_key",
            None,
        )
        if graph_metric_key in metric_names_by_key:
            show_performance_stat_graph(
                build_core_performance_trend(
                    weekly_rows,
                    selected_stat,
                    str(graph_metric_key),
                ),
                selected_stat,
                metric_names_by_key[str(graph_metric_key)],
                selected_season,
            )
    else:
        st.info("No completed-game statistics are available for this player.")

    render_data_disclaimer(data_update, *comparison_updates)

    return (
        weekly_rows,
        data_update,
        comparison_updates,
        position_rows_by_player_id,
        position_player_ids,
    )
