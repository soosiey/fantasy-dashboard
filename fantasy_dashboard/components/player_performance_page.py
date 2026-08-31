from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from fantasy_dashboard.components.player_performance_availability_tab import (
    render_availability_tab,
)
from fantasy_dashboard.components.player_performance_consistency_tab import (
    render_consistency_tab,
)
from fantasy_dashboard.components.player_performance_core_tab import (
    render_core_performance_tab,
)
from fantasy_dashboard.components.player_performance_projection_tab import (
    render_projection_accuracy_tab,
)
from fantasy_dashboard.components.player_performance_usage_tabs import (
    render_efficiency_tab,
    render_opportunity_tab,
)
from fantasy_dashboard.data import get_current_nfl_season, get_league
from fantasy_dashboard.player_stats import get_relevant_stat_fields
from fantasy_dashboard.routing import sync_query_params


def _render_player_heading(player_id: str, player: dict[str, Any]) -> tuple[str, str]:
    player_name = (
        f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
    ).strip()
    position = str(player.get("position") or "—")
    team = str(player.get("team") or "FA")
    st.header(player_name or player_id)
    player_details = [team, position]
    number = player.get("number")
    if number not in (None, ""):
        player_details.append(f"#{number}")
    st.caption(" · ".join(player_details))
    return position, team


def _render_season_and_stat_controls(
    league_id: str,
    player_id: str,
    position: str,
) -> tuple[str, str]:
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
        selected_season = st.selectbox("Year", season_options, key=season_key)
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
    return selected_season, selected_stat


def render_player_performance(
    league_id: str,
    player_id: str,
    players: dict[str, dict[str, Any]],
    player: dict[str, Any],
) -> None:
    position, team = _render_player_heading(player_id, player)
    selected_season, selected_stat = _render_season_and_stat_controls(
        league_id,
        player_id,
        position,
    )
    league = get_league(league_id)

    (
        core_tab,
        projection_tab,
        consistency_tab,
        opportunity_tab,
        efficiency_tab,
        availability_tab,
    ) = st.tabs(
        [
            "Core Performance Statistics",
            "Projection Accuracy",
            "Consistency",
            "Opportunity",
            "Efficiency",
            "Availability",
        ]
    )

    with core_tab:
        (
            weekly_rows,
            data_update,
            comparison_updates,
            position_rows_by_player_id,
            position_player_ids,
        ) = render_core_performance_tab(
            league_id,
            player_id,
            players,
            position,
            league,
            selected_season,
            selected_stat,
        )

    with projection_tab:
        (
            projected_rows,
            position_projected_rows_by_player_id,
            projection_updates,
        ) = render_projection_accuracy_tab(
            league_id,
            player_id,
            position,
            league,
            selected_season,
            selected_stat,
            weekly_rows,
            data_update,
            position_rows_by_player_id,
            position_player_ids,
        )

    with consistency_tab:
        render_consistency_tab(
            league_id,
            player_id,
            position,
            selected_season,
            selected_stat,
            weekly_rows,
            projected_rows,
            position_rows_by_player_id,
            position_projected_rows_by_player_id,
            position_player_ids,
            data_update,
            projection_updates,
        )

    shared_usage_args = (
        position,
        selected_season,
        weekly_rows,
        position_rows_by_player_id,
        position_player_ids,
        data_update,
        comparison_updates,
    )
    with opportunity_tab:
        render_opportunity_tab(*shared_usage_args)
    with efficiency_tab:
        render_efficiency_tab(*shared_usage_args)
    with availability_tab:
        render_availability_tab(
            players,
            player,
            position,
            team,
            selected_season,
            weekly_rows,
            position_rows_by_player_id,
            position_player_ids,
            data_update,
            comparison_updates,
        )
