from numbers import Real
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from fantasy_dashboard.components.comparison_data import (
    FULL_SEASON_WEEKS,
    ComparisonDataProvider,
)
from fantasy_dashboard.components.comparison_graph_controls import (
    ComparisonGraphSettings,
    render_comparison_graph_settings,
)
from fantasy_dashboard.components.comparison_graph_metrics import (
    MAX_GRAPH_STATISTICS,
    build_comparison_category_statistics,
    get_comparison_metric_options,
    get_comparison_player_name,
)
from fantasy_dashboard.player_performance import (
    build_availability_statistics,
    build_availability_trend,
    build_consistency_trend,
    build_core_performance_trend,
    build_efficiency_trend,
    build_opportunity_trend,
    build_projection_accuracy_trend,
    get_team_completed_weeks,
)


def _render_metric_selector(
    league_id: str,
    season: str,
    metric_options: list[dict[str, str]],
) -> list[dict[str, str]]:
    metric_key_prefix = f"comparison-weekly-graphs-{league_id}-{season}-metric"
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
    return [
        option
        for option in metric_options
        if st.session_state.get(f"{metric_key_prefix}-{option['id']}", False)
    ]


def _metric_trend(
    category: str,
    metric_key: str,
    player_id: str,
    players: dict[str, dict[str, Any]],
    actual_rows: dict[str, list[dict[str, Any]]],
    projected_rows: dict[str, list[dict[str, Any]]],
    schedule: list[dict[str, Any]],
    selected_stat: str,
    graph_settings: ComparisonGraphSettings,
) -> list[dict[str, Any]]:
    if category == "Core Performance":
        return build_core_performance_trend(
            actual_rows[player_id], selected_stat, metric_key
        )
    if category == "Projection Accuracy":
        return build_projection_accuracy_trend(
            actual_rows[player_id],
            projected_rows[player_id],
            selected_stat,
            metric_key,
            hit_tolerance=graph_settings.hit_tolerance,
        )
    if category == "Consistency":
        return build_consistency_trend(
            actual_rows[player_id],
            projected_rows[player_id],
            selected_stat,
            metric_key,
            consistency_band_percent=graph_settings.consistency_band_percent,
            boom_bust_tolerance=graph_settings.boom_bust_tolerance,
        )
    position = str(players[player_id].get("position") or "")
    if category == "Opportunity":
        return build_opportunity_trend(actual_rows[player_id], position, metric_key)
    if category == "Efficiency":
        return build_efficiency_trend(actual_rows[player_id], position, metric_key)
    completed_weeks = get_team_completed_weeks(
        schedule,
        str(players[player_id].get("team") or ""),
    )
    return build_availability_trend(
        actual_rows[player_id],
        completed_weeks,
        str(players[player_id].get("injury_status") or ""),
        metric_key,
    )


def render_comparison_weekly_graphs(
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
    year_key = f"comparison-weekly-graphs-{league_id}-year"
    if st.session_state.get(year_key) not in season_options:
        st.session_state[year_key] = season_options[0]
    selected_season = st.selectbox("Year", season_options, key=year_key)

    selected_positions = data_provider.selected_positions
    positions_are_compatible = data_provider.positions_are_compatible
    stat_options = data_provider.get_stat_options()
    stat_key = f"comparison-weekly-graphs-{league_id}-stat"
    if st.session_state.get(stat_key) not in stat_options:
        st.session_state[stat_key] = "Fantasy Points"
    selected_stat = st.selectbox("Stat", stat_options, key=stat_key)

    context = data_provider.get_context(selected_season, FULL_SEASON_WEEKS)
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
        list(FULL_SEASON_WEEKS),
        selected_stat,
        positions_are_compatible,
    )
    if not positions_are_compatible:
        category_statistics["Availability"] = {}
        for player_id in league_player_ids:
            completed_weeks = get_team_completed_weeks(
                schedule,
                str(players[player_id].get("team") or ""),
            )
            category_statistics["Availability"][player_id] = (
                build_availability_statistics(
                    actual_rows[player_id],
                    len(completed_weeks) if schedule else None,
                    str(players[player_id].get("injury_status") or ""),
                )
            )
    metric_options = get_comparison_metric_options(
        category_statistics,
        selected_player_ids,
    )
    selected_options = _render_metric_selector(
        league_id,
        selected_season,
        metric_options,
    )
    if not selected_options:
        st.info("Select at least one performance statistic to graph.")
        return

    graph_settings = render_comparison_graph_settings(
        selected_options,
        key_prefix=f"comparison-weekly-graphs-{league_id}-{selected_season}",
    )

    selected_positions = list(dict.fromkeys(selected_positions))
    metric_charts = []
    for option in selected_options:
        player_trends = {
            player_id: _metric_trend(
                option["category"],
                option["key"],
                player_id,
                players,
                actual_rows,
                projected_rows,
                schedule,
                selected_stat,
                graph_settings,
            )
            for player_id in league_player_ids
        }
        chart_rows: list[dict[str, Any]] = []
        for player_id in selected_player_ids:
            for row in player_trends[player_id]:
                value = row.get("Value")
                if isinstance(value, Real) and not isinstance(value, bool):
                    chart_rows.append(
                        {
                            "Week": int(row["Week"]),
                            "Entity": get_comparison_player_name(
                                player_id,
                                players,
                            ),
                            "Value": float(value),
                            "Series": "Player",
                        }
                    )
        for position in selected_positions:
            position_player_ids = [
                player_id
                for player_id in league_player_ids
                if str(players[player_id].get("position") or "") == position
            ]
            values_by_week: dict[int, list[float]] = {}
            for player_id in position_player_ids:
                for row in player_trends[player_id]:
                    value = row.get("Value")
                    if isinstance(value, Real) and not isinstance(value, bool):
                        values_by_week.setdefault(int(row["Week"]), []).append(
                            float(value)
                        )
            for week, values in sorted(values_by_week.items()):
                chart_rows.append(
                    {
                        "Week": week,
                        "Entity": f"{position} League Average",
                        "Value": float(np.mean(values)),
                        "Series": "League Average",
                    }
                )
        if not chart_rows:
            continue
        chart_data = pd.DataFrame(chart_rows)
        entity_order = list(dict.fromkeys(chart_data["Entity"].astype(str)))
        color = alt.Color(
            "Entity:N",
            title=None,
            sort=entity_order,
        )
        encoding = {
            "x": alt.X(
                "Week:O",
                title=None,
                sort=list(range(1, 19)),
                axis=alt.Axis(labelAngle=0),
            ),
            "y": alt.Y("Value:Q", title=None),
            "color": color,
            "tooltip": [
                alt.Tooltip("Entity:N"),
                alt.Tooltip("Week:O"),
                alt.Tooltip("Value:Q", format=".2f"),
            ],
        }
        player_chart = (
            alt.Chart(chart_data)
            .transform_filter(alt.datum.Series == "Player")
            .mark_line(point=True)
            .encode(**encoding)
        )
        average_chart = (
            alt.Chart(chart_data)
            .transform_filter(alt.datum.Series == "League Average")
            .mark_line(point=True, strokeDash=[6, 4])
            .encode(**encoding)
        )
        metric_charts.append(
            (player_chart + average_chart).properties(
                width=1200,
                height=320,
                title=alt.TitleParams(
                    text=option["label"],
                    anchor="start",
                    offset=12,
                    fontSize=16,
                ),
            )
        )

    if not metric_charts:
        st.info("The selected statistics have no weekly values for this season.")
        return
    st.altair_chart(
        alt.vconcat(*metric_charts).resolve_scale(y="independent"),
        width="stretch",
    )
