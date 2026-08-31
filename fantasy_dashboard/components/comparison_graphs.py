from datetime import datetime
from numbers import Real
from typing import Any
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.comparison_performance import (
    comparison_positions_are_compatible,
    get_comparison_stat_options,
)
from fantasy_dashboard.data import (
    get_current_nfl_season,
    get_nfl_schedule,
    get_player_stats,
    get_projected_player_stats,
    get_rosters,
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
    is_eligible_game,
)
from fantasy_dashboard.player_stats import build_player_stat_row

MAX_GRAPH_STATISTICS = 5


def _player_name(player_id: str, players: dict[str, dict[str, Any]]) -> str:
    player = players.get(player_id, {})
    name = f"{player.get('first_name') or ''} {player.get('last_name') or ''}".strip()
    position = str(player.get("position") or "—")
    return f"{name or player_id} ({position})"


def _season_options() -> list[str]:
    try:
        current_season = int(get_current_nfl_season())
    except (requests.RequestException, KeyError, TypeError, ValueError):
        today = datetime.now(ZoneInfo("America/New_York")).date()
        current_season = today.year if today.month >= 3 else today.year - 1
        st.warning("The current NFL season could not be detected from Sleeper.")
    return [str(current_season - offset) for offset in range(3)]


def _load_weekly_rows(
    player_ids: list[str],
    season: str,
    weeks: list[int],
    scoring_settings: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    actual_rows = {player_id: [] for player_id in player_ids}
    projected_rows = {player_id: [] for player_id in player_ids}
    for week in weeks:
        actual_stats = get_player_stats(season, "regular", week)
        projected_stats = get_projected_player_stats(season, week)
        for player_id in player_ids:
            player_actual_stats = actual_stats.get(player_id, {})
            if is_eligible_game({"stats": player_actual_stats}):
                row = build_player_stat_row(
                    player_actual_stats,
                    scoring_settings,
                    week,
                    stats_available=True,
                )
                row["_Raw Stats"] = player_actual_stats
                actual_rows[player_id].append(row)
            player_projected_stats = projected_stats.get(player_id, {})
            if player_projected_stats:
                projected_rows[player_id].append(
                    build_player_stat_row(
                        player_projected_stats,
                        scoring_settings,
                        week,
                        stats_available=True,
                    )
                )
    return actual_rows, projected_rows


def _build_category_statistics(
    player_ids: list[str],
    players: dict[str, dict[str, Any]],
    actual_rows: dict[str, list[dict[str, Any]]],
    projected_rows: dict[str, list[dict[str, Any]]],
    schedule: list[dict[str, Any]],
    selected_weeks: list[int],
    selected_stat: str,
    positions_are_compatible: bool,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    categories = {
        "Core Performance": {
            player_id: build_core_performance_statistics(
                actual_rows[player_id], selected_stat
            )
            for player_id in player_ids
        },
        "Projection Accuracy": {
            player_id: build_projection_accuracy_statistics(
                actual_rows[player_id],
                projected_rows[player_id],
                selected_stat,
                hit_tolerance=3.0,
            )
            for player_id in player_ids
        },
        "Consistency": {
            player_id: build_consistency_statistics(
                actual_rows[player_id],
                projected_rows[player_id],
                selected_stat,
                consistency_band_percent=20.0,
                boom_bust_tolerance=3.0,
            )
            for player_id in player_ids
        },
    }
    if positions_are_compatible:
        categories["Opportunity"] = {
            player_id: build_opportunity_statistics(
                actual_rows[player_id],
                str(players[player_id].get("position") or ""),
            )
            for player_id in player_ids
        }
        categories["Efficiency"] = {
            player_id: build_efficiency_statistics(
                actual_rows[player_id],
                str(players[player_id].get("position") or ""),
            )
            for player_id in player_ids
        }

    if positions_are_compatible:
        selected_week_set = set(selected_weeks)
        categories["Availability"] = {}
        for player_id in player_ids:
            player = players[player_id]
            completed_weeks = [
                week
                for week in get_team_completed_weeks(
                    schedule,
                    str(player.get("team") or ""),
                )
                if week in selected_week_set
            ]
            categories["Availability"][player_id] = build_availability_statistics(
                actual_rows[player_id],
                len(completed_weeks) if schedule else None,
                str(player.get("injury_status") or ""),
            )
    return categories


def _metric_options(
    category_statistics: dict[str, dict[str, list[dict[str, Any]]]],
    selected_player_ids: list[str],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for category, statistics_by_player in category_statistics.items():
        for player_id in selected_player_ids:
            for metric in statistics_by_player.get(player_id, []):
                if metric["Key"] == "injury_status":
                    continue
                option_id = f"{category}:{metric['Key']}"
                if option_id in seen:
                    continue
                seen.add(option_id)
                options.append(
                    {
                        "id": option_id,
                        "category": category,
                        "key": str(metric["Key"]),
                        "label": f"{category} · {metric['Statistic']}",
                    }
                )
    return options


def render_comparison_graphs(
    league_id: str,
    league: Any,
    players: dict[str, dict[str, Any]],
    comparison_player_ids: list[str],
) -> None:
    selected_player_ids = [
        player_id for player_id in comparison_player_ids if player_id in players
    ]
    if not selected_player_ids:
        st.info("No visible checked players were included in this comparison.")
        return

    season_options = _season_options()
    year_key = f"comparison-graphs-{league_id}-year"
    if st.session_state.get(year_key) not in season_options:
        st.session_state[year_key] = season_options[0]
    selected_season = st.selectbox("Year", season_options, key=year_key)

    selected_positions = [
        str(players[player_id].get("position") or "")
        for player_id in selected_player_ids
    ]
    positions_are_compatible = comparison_positions_are_compatible(
        selected_positions
    )
    stat_options = get_comparison_stat_options(players, selected_player_ids)
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

    try:
        rosters = get_rosters(league_id)
        rostered_player_ids = {
            str(player_id)
            for roster in rosters.rosters
            for player_id in roster.players
            if player_id is not None and str(player_id) in players
        }
    except (requests.RequestException, TypeError, ValueError, AttributeError):
        rostered_player_ids = set(selected_player_ids)
        st.warning("League rosters could not be loaded for the league averages.")
    league_player_ids = sorted(rostered_player_ids | set(selected_player_ids))

    try:
        actual_rows, projected_rows = _load_weekly_rows(
            league_player_ids,
            selected_season,
            selected_weeks,
            league.scoring_settings,
        )
    except (requests.RequestException, TypeError, ValueError):
        st.warning("Player statistics could not be loaded for the selected weeks.")
        return
    try:
        schedule = get_nfl_schedule(selected_season, "regular")
    except (requests.RequestException, TypeError, ValueError):
        schedule = []

    if not positions_are_compatible:
        st.warning(
            "You have selected players from different position groups, so only "
            "fantasy-point performance statistics will be compared."
        )
    category_statistics = _build_category_statistics(
        league_player_ids,
        players,
        actual_rows,
        projected_rows,
        schedule,
        selected_weeks,
        selected_stat,
        positions_are_compatible,
    )
    metric_options = _metric_options(category_statistics, selected_player_ids)
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
                        "Entity": _player_name(player_id, players),
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
