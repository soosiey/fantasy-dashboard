from typing import Any

import pandas as pd
import streamlit as st

from fantasy_dashboard.models.league import LeagueModel, RosterContainer
from fantasy_dashboard.models.user import UserContainer
from fantasy_dashboard.player_stats import (
    build_player_identity_image,
    build_player_roster_labels,
    build_player_stat_rows,
    get_rosterable_positions,
)
from fantasy_dashboard.routing import (
    ANALYSIS_MODE_KEY,
    PLAYER_STATS_MODE_KEY,
    PLAYER_STATS_PENDING_KEY,
    sync_query_params,
)


def _open_graph_from_button(click_key: str, player_ids: list[str]) -> None:
    click = st.session_state.get(click_key)
    if not click:
        return
    selected_row = int(click["row"])
    if 0 <= selected_row < len(player_ids):
        st.session_state["_graph_target_player_id"] = player_ids[selected_row]


def render_graph_player_picker(
    league_id: str,
    league: LeagueModel,
    rosters: RosterContainer,
    teams: UserContainer,
    nfl_players: dict[str, dict[str, Any]],
) -> None:
    rosterable_positions = get_rosterable_positions(league.roster_positions)
    roster_labels = build_player_roster_labels(rosters.rosters, teams.users)
    requested_position = str(st.query_params.get("position") or "")
    position_filter_options = ["All Positions", "FLEX", *rosterable_positions]
    position_filter_key = f"graphs-{league_id}-position"
    search_filter_key = f"graphs-{league_id}-search"
    if position_filter_key not in st.session_state:
        st.session_state[position_filter_key] = (
            requested_position
            if requested_position in position_filter_options
            else "All Positions"
        )
    if search_filter_key not in st.session_state:
        st.session_state[search_filter_key] = str(st.query_params.get("search") or "")

    position_column, search_column = st.columns([1, 3])
    with position_column:
        selected_position_label = st.selectbox(
            "Position",
            position_filter_options,
            key=position_filter_key,
        )
    with search_column:
        player_search = st.text_input(
            "Player name",
            placeholder="Search by player name",
            key=search_filter_key,
        )

    sync_query_params(
        league_id=league_id,
        position=(
            selected_position_label
            if selected_position_label != "All Positions"
            else None
        ),
        search=player_search.strip() or None,
    )

    selected_position = (
        None if selected_position_label == "All Positions" else selected_position_label
    )
    player_rows = build_player_stat_rows(
        nfl_players,
        rosters.rosters,
        {},
        league.scoring_settings,
        rosterable_positions,
        selected_position=selected_position,
        roster_labels_by_player_id=roster_labels,
    )
    search_query = player_search.strip().casefold()
    if search_query:
        player_rows = [
            row for row in player_rows if search_query in str(row["Player"]).casefold()
        ]

    st.caption(f"{len(player_rows):,} players")
    if not player_rows:
        st.info("No players match the selected filters.")
    else:
        player_table = pd.DataFrame(player_rows)
        player_ids = player_table["Player ID"].astype(str).tolist()
        player_table["Player"] = [
            build_player_identity_image(player, owner)
            for player, owner in zip(player_table["Player"], player_table["Roster"])
        ]
        player_table = player_table[["Player ID", "Player"]]
        player_table["Graph"] = "Open"

        st.dataframe(
            player_table,
            column_config={
                "Player ID": None,
                "Player": st.column_config.ImageColumn("Player", width="large"),
                "Graph": st.column_config.ButtonColumn(
                    "",
                    width="small",
                    type="secondary",
                    on_click=_open_graph_from_button,
                    args=("graphs-player-click", player_ids),
                    key="graphs-player-click",
                ),
            },
            hide_index=True,
            height=700,
            width="stretch",
            key="graphs-player-table",
        )

    selected_graph_player_id = st.session_state.pop("_graph_target_player_id", None)
    if selected_graph_player_id:
        st.session_state["graph_player_id"] = str(selected_graph_player_id)
        st.session_state[PLAYER_STATS_MODE_KEY] = True
        st.session_state[PLAYER_STATS_PENDING_KEY] = True
        st.session_state.pop(ANALYSIS_MODE_KEY, None)
        # Restart at the entrypoint so it can route before rendering the new sidebar.
        st.rerun()
