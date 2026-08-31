from typing import Any

import altair as alt
import pandas as pd
import streamlit as st


def open_performance_stat_graph(
    click_key: str,
    metric_keys: list[str],
    selection_state_key: str,
) -> None:
    """Resolve a dataframe button click to the metric on that row."""
    click = st.session_state.get(click_key)
    if not click:
        return
    selected_row = int(click["row"])
    if 0 <= selected_row < len(metric_keys):
        st.session_state[selection_state_key] = metric_keys[selected_row]


@st.dialog("Performance Graph", width="large")
def show_performance_stat_graph(
    trend_rows: list[dict[str, Any]],
    selected_stat: str,
    metric_name: str,
    season: str,
) -> None:
    """Plot how a derived metric changed as completed games accumulated."""
    st.subheader(f"{metric_name} · {selected_stat}")
    st.caption(
        f"{season} season · Each point recalculates the statistic through that week."
    )
    chart_data = pd.DataFrame(trend_rows)
    if chart_data.empty or chart_data["Value"].notna().sum() == 0:
        st.info("There is not enough completed-game data to graph this statistic.")
        return

    chart = (
        alt.Chart(chart_data)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "Week Label:N",
                sort=alt.SortField(field="Week", order="ascending"),
                title=None,
                axis=alt.Axis(labelAngle=-45, labelAlign="right", labelLimit=140),
            ),
            y=alt.Y("Value:Q", title=selected_stat),
            tooltip=[
                alt.Tooltip("Week Label:N", title="Week"),
                alt.Tooltip("Value:Q", title=metric_name, format=".2f"),
            ],
        )
        .properties(height=420)
    )
    st.altair_chart(chart, width="stretch")
