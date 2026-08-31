from numbers import Real
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from fantasy_dashboard.components.comparison_data import (
    ComparisonDataProvider,
)
from fantasy_dashboard.components.comparison_graph_controls import (
    render_comparison_graph_settings,
)
from fantasy_dashboard.components.comparison_graph_metrics import (
    MAX_GRAPH_STATISTICS,
    build_comparison_category_statistics,
    get_comparison_metric_options,
    get_comparison_player_name,
)
from fantasy_dashboard.player_performance import (
    build_metric_average_values,
)


def render_comparison_graphs(
    data_provider: ComparisonDataProvider,
) -> None:
    league_id = data_provider.league_id
    players = data_provider.players
    selected_player_ids = data_provider.selected_player_ids
    if not selected_player_ids:
        st.info("No visible checked players were included in this comparison.")
        return

    season_options = data_provider.get_season_options()
    if data_provider.season_warning:
        st.warning(data_provider.season_warning)
    year_key = f"comparison-graphs-{league_id}-year"
    if st.session_state.get(year_key) not in season_options:
        st.session_state[year_key] = season_options[0]
    selected_season = st.selectbox("Year", season_options, key=year_key)

    selected_positions = data_provider.selected_positions
    positions_are_compatible = data_provider.positions_are_compatible
    stat_options = data_provider.get_stat_options()
    stat_key = f"comparison-graphs-{league_id}-stat"
    if st.session_state.get(stat_key) not in stat_options:
        st.session_state[stat_key] = "Fantasy Points"
    selected_stat = st.selectbox("Stat", stat_options, key=stat_key)

    week_key_prefix = f"comparison-graphs-{league_id}-{selected_season}-week"
    week_keys = [f"{week_key_prefix}-{week}" for week in range(1, 19)]
    for week_key in week_keys:
        if week_key not in st.session_state:
            st.session_state[week_key] = True
    if st.button(
        "Check/Uncheck All",
        key=f"comparison-graphs-{league_id}-{selected_season}-toggle-weeks",
    ):
        new_value = not all(bool(st.session_state[key]) for key in week_keys)
        for week_key in week_keys:
            st.session_state[week_key] = new_value
        st.rerun()

    st.caption("Weeks")
    week_columns = st.columns(6)
    for week in range(1, 19):
        with week_columns[(week - 1) % len(week_columns)]:
            st.checkbox(f"Week {week}", key=week_keys[week - 1])
    selected_weeks = [
        week for week, key in enumerate(week_keys, start=1) if st.session_state[key]
    ]
    if not selected_weeks:
        st.warning("Select at least one week to build comparison graphs.")
        return

    context = data_provider.get_context(selected_season, selected_weeks)
    for warning in context.warnings:
        st.warning(warning)
    league_player_ids = context.league_player_ids
    actual_rows = context.actual_rows
    projected_rows = context.projected_rows
    schedule = context.schedule

    if not positions_are_compatible:
        st.warning(
            "You have selected players from different position groups, so only "
            "fantasy-point performance statistics will be compared."
        )
    category_statistics = build_comparison_category_statistics(
        league_player_ids,
        players,
        actual_rows,
        projected_rows,
        schedule,
        selected_weeks,
        selected_stat,
        positions_are_compatible,
    )
    metric_options = get_comparison_metric_options(
        category_statistics,
        selected_player_ids,
    )
    option_ids = {option["id"] for option in metric_options}
    metric_key_prefix = f"comparison-graphs-{league_id}-{selected_season}-metric"
    selected_metric_ids = [
        option["id"]
        for option in metric_options
        if st.session_state.get(f"{metric_key_prefix}-{option['id']}", False)
    ]
    if len(selected_metric_ids) > MAX_GRAPH_STATISTICS:
        for option_id in selected_metric_ids[MAX_GRAPH_STATISTICS:]:
            st.session_state[f"{metric_key_prefix}-{option_id}"] = False
        selected_metric_ids = selected_metric_ids[:MAX_GRAPH_STATISTICS]

    st.caption(f"Statistics · Select up to {MAX_GRAPH_STATISTICS}")
    with st.container(height=340, border=True):
        for option in metric_options:
            checkbox_key = f"{metric_key_prefix}-{option['id']}"
            st.checkbox(
                option["label"],
                key=checkbox_key,
                disabled=(
                    len(selected_metric_ids) >= MAX_GRAPH_STATISTICS
                    and option["id"] not in selected_metric_ids
                ),
            )

    selected_metric_ids = [
        option_id
        for option_id in option_ids
        if st.session_state.get(f"{metric_key_prefix}-{option_id}", False)
    ]
    selected_options = [
        option for option in metric_options if option["id"] in selected_metric_ids
    ]
    if not selected_options:
        st.info("Select at least one performance statistic to graph.")
        return

    graph_settings = render_comparison_graph_settings(
        selected_options,
        key_prefix=f"comparison-graphs-{league_id}-{selected_season}",
    )
    category_statistics = build_comparison_category_statistics(
        league_player_ids,
        players,
        actual_rows,
        projected_rows,
        schedule,
        selected_weeks,
        selected_stat,
        positions_are_compatible,
        hit_tolerance=graph_settings.hit_tolerance,
        consistency_band_percent=graph_settings.consistency_band_percent,
        boom_bust_tolerance=graph_settings.boom_bust_tolerance,
    )

    selected_positions = list(dict.fromkeys(selected_positions))
    chart_rows: list[dict[str, Any]] = []
    for option in selected_options:
        statistics_by_player = category_statistics[option["category"]]
        values_by_player = {
            player_id: {
                str(metric["Key"]): metric.get("Value") for metric in statistics
            }
            for player_id, statistics in statistics_by_player.items()
        }
        for player_id in selected_player_ids:
            value = values_by_player.get(player_id, {}).get(option["key"])
            if isinstance(value, Real) and not isinstance(value, bool):
                chart_rows.append(
                    {
                        "Statistic": option["label"],
                        "Entity": get_comparison_player_name(player_id, players),
                        "Value": float(value),
                        "Series": "Player",
                    }
                )
        for position in selected_positions:
            position_averages = build_metric_average_values(
                {
                    player_id: statistics
                    for player_id, statistics in statistics_by_player.items()
                    if str(players[player_id].get("position") or "") == position
                }
            )
            value = position_averages.get(option["key"])
            if value is not None:
                chart_rows.append(
                    {
                        "Statistic": option["label"],
                        "Entity": f"{position} League Average",
                        "Value": float(value),
                        "Series": "League Average",
                    }
                )

    if not chart_rows:
        st.info("The selected statistics have no values for these weeks.")
        return
    chart_data = pd.DataFrame(chart_rows)
    entity_order = list(dict.fromkeys(chart_data["Entity"].astype(str)))
    metric_charts = []
    for option in selected_options:
        metric_chart_data = chart_data[chart_data["Statistic"] == option["label"]]
        if metric_chart_data.empty:
            continue
        metric_charts.append(
            alt.Chart(metric_chart_data)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Entity:N",
                    title=None,
                    sort=entity_order,
                    axis=alt.Axis(
                        labelAngle=-45,
                        labelAlign="right",
                        labelLimit=240,
                        labelOverlap=False,
                    ),
                ),
                y=alt.Y("Value:Q", title=None),
                color=alt.Color(
                    "Series:N",
                    title=None,
                    scale=alt.Scale(
                        domain=["Player", "League Average"],
                        range=["#4c78a8", "#f58518"],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("Statistic:N"),
                    alt.Tooltip("Entity:N"),
                    alt.Tooltip("Value:Q", format=".2f"),
                ],
            )
            .properties(
                width=1200,
                height=260,
                title=alt.TitleParams(
                    text=option["label"],
                    anchor="start",
                    offset=12,
                    fontSize=16,
                ),
            )
        )
    chart = alt.vconcat(*metric_charts).resolve_scale(y="independent")
    st.altair_chart(chart, width="stretch")
