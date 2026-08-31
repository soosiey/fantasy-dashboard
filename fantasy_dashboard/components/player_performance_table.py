import pandas as pd
import streamlit as st

from fantasy_dashboard.components.player_performance_graph import (
    open_performance_stat_graph,
)


def render_metric_table(
    statistics: list[dict],
    position: str,
    position_averages: dict[str, float],
    *,
    click_key: str,
    selection_state_key: str,
) -> dict[str, str]:
    statistics_table = pd.DataFrame(statistics)
    metric_keys = statistics_table["Key"].astype(str).tolist()
    metric_names_by_key = {str(row["Key"]): str(row["Statistic"]) for row in statistics}
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
        for metric_key, value in zip(metric_keys, statistics_table["Value"])
    ]
    statistics_table = statistics_table[
        [
            "Statistic",
            "Value",
            league_average_column,
            difference_column,
            "Unit",
            "Context",
        ]
    ].copy()
    statistics_table["View Graph"] = [
        "View" if row.get("Graphable", True) else "" for row in statistics
    ]
    st.dataframe(
        statistics_table,
        column_config={
            "Statistic": st.column_config.TextColumn("Statistic", width="medium"),
            "Value": st.column_config.NumberColumn(
                "Value",
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
            "Unit": st.column_config.TextColumn("Unit", width="small"),
            "Context": st.column_config.TextColumn("Context", width="large"),
            "View Graph": st.column_config.ButtonColumn(
                "View Graph",
                width="small",
                type="secondary",
                on_click=open_performance_stat_graph,
                args=(click_key, metric_keys, selection_state_key),
                key=click_key,
            ),
        },
        hide_index=True,
        width="stretch",
    )
    return metric_names_by_key
