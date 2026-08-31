from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.player_performance_graph import (
    open_performance_stat_graph,
    show_performance_stat_graph,
)
from fantasy_dashboard.data import (
    get_current_nfl_season,
    get_data_update,
    get_league,
    get_nfl_players,
    get_player_stats,
    get_player_weekly_stats,
    get_projected_player_stats,
    get_rosters,
)
from fantasy_dashboard.graph_stats import build_actual_weekly_stat_rows
from fantasy_dashboard.player_performance import (
    build_consistency_statistics,
    build_consistency_trend,
    build_core_performance_statistics,
    build_core_performance_trend,
    build_metric_average_values,
    build_position_average_statistics,
    build_projection_accuracy_statistics,
    build_projection_accuracy_trend,
    is_eligible_game,
)
from fantasy_dashboard.player_stats import (
    build_player_stat_row,
    get_relevant_stat_fields,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PLAYER_STATS_MODE_KEY,
    require_authentication,
    resolve_context_id,
    resolve_league_id,
    sync_query_params,
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
    statistics_table["View Graph"] = "View"
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


require_authentication("performance")
league_id = resolve_league_id()

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

player_id = resolve_context_id("player_id", "graph_player_id")
if player_id is None:
    st.warning("Select a player first.")
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page("pages/graphs.py", query_params={"league_id": league_id})

if not st.session_state.get(PLAYER_STATS_MODE_KEY):
    st.session_state[PLAYER_STATS_MODE_KEY] = True
    st.session_state.pop(ANALYSIS_MODE_KEY, None)
    st.rerun()

st.title("Performance")

players = get_nfl_players()
player = players.get(player_id)
if player is None:
    st.warning("That player could not be found in the local player cache.")
else:
    player_name = (
        f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
    ).strip()
    position = str(player.get("position") or "—")
    team = str(player.get("team") or "FA")
    number = player.get("number")
    st.header(player_name or player_id)
    player_details = [team, position]
    if number not in (None, ""):
        player_details.append(f"#{number}")
    st.caption(" · ".join(player_details))

    league = get_league(league_id)
    try:
        current_season = int(get_current_nfl_season())
    except (requests.RequestException, KeyError, TypeError, ValueError):
        today = datetime.now(ZoneInfo("America/New_York")).date()
        current_season = today.year if today.month >= 3 else today.year - 1
        st.warning("The current NFL season could not be detected from Sleeper.")

    season_options = [str(current_season - offset) for offset in range(3)]
    relevant_stat_options = [
        label
        for label, stat_key in get_relevant_stat_fields(position)
        if stat_key != "gp"
    ]
    requested_season = str(st.query_params.get("year") or "")
    requested_stat = str(st.query_params.get("stat") or "")
    season_key = f"performance-{league_id}-{player_id}-year"
    stat_key = f"performance-{league_id}-{player_id}-stat"
    if season_key not in st.session_state:
        st.session_state[season_key] = (
            requested_season
            if requested_season in season_options
            else season_options[0]
        )
    if stat_key not in st.session_state:
        st.session_state[stat_key] = (
            requested_stat
            if requested_stat in relevant_stat_options
            else "Fantasy Points"
        )
    if st.session_state[season_key] not in season_options:
        st.session_state[season_key] = season_options[0]
    if st.session_state[stat_key] not in relevant_stat_options:
        st.session_state[stat_key] = "Fantasy Points"

    year_column, stat_column = st.columns(2)
    with year_column:
        selected_season = st.selectbox(
            "Year",
            season_options,
            key=season_key,
        )
    with stat_column:
        selected_stat = st.selectbox(
            "Stat",
            relevant_stat_options,
            key=stat_key,
        )
    sync_query_params(
        league_id=league_id,
        player_id=player_id,
        year=selected_season,
        stat=selected_stat,
    )

    core_performance_tab, projection_accuracy_tab, consistency_tab = st.tabs(
        ["Core Performance Statistics", "Projection Accuracy", "Consistency"]
    )
    weekly_rows: list[dict] = []
    data_update = None
    comparison_updates = []
    position_rows_by_player_id: dict[str, list[dict]] = {}
    position_player_ids: list[str] = []
    with core_performance_tab:
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
                        position_rows_by_player_id[position_player_id].append(
                            build_player_stat_row(
                                player_week_stats,
                                league.scoring_settings,
                                week,
                                stats_available=True,
                            )
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

    with projection_accuracy_tab:
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

    with consistency_tab:
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

with st.bottom:
    back_to_analysis = st.button("Back to Analysis")

if back_to_analysis:
    st.session_state.pop(PLAYER_STATS_MODE_KEY, None)
    st.session_state[ANALYSIS_MODE_KEY] = True
    st.switch_page(
        "pages/graphs.py",
        query_params={"league_id": league_id},
    )
