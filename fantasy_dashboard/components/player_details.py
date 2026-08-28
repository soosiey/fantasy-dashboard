from typing import Any

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.data import get_player_weekly_stats
from fantasy_dashboard.player_stats import (
    build_player_weekly_stat_rows,
    get_relevant_stat_labels,
)


# Show player identity and an 18-week, league-scored game log in a wide modal.
@st.dialog("Player Details", width="large")
def show_player_details(
    player_id: str,
    player: dict[str, Any],
    season: str,
    season_type: str,
    scoring_settings: dict[str, Any],
) -> None:
    player_name = (
        f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
    ).strip()
    position = str(player.get("position") or "—")
    team = str(player.get("team") or "FA")
    number = player.get("number")

    st.header(player_name or player_id)
    details = [team, position]
    if number not in (None, ""):
        details.append(f"#{number}")
    st.caption(" · ".join(details))

    try:
        with st.spinner("Loading weekly statistics..."):
            weekly_stats = get_player_weekly_stats(
                player_id, season, season_type
            )
    except (requests.RequestException, TypeError, ValueError):
        st.warning("Weekly player statistics could not be loaded.")
        return

    weekly_table = pd.DataFrame(
        build_player_weekly_stat_rows(weekly_stats, scoring_settings)
    )

    def highlight_relevant_stats(row: pd.Series) -> list[str]:
        relevant_columns = get_relevant_stat_labels(position)
        return [
            "background-color: rgba(59, 130, 246, 0.10)"
            if column in relevant_columns
            else ""
            for column in row.index
        ]

    st.dataframe(
        weekly_table.style.apply(highlight_relevant_stats, axis=1),
        column_config={
            "Week": st.column_config.NumberColumn("Week", width="small"),
            "Opponent": st.column_config.TextColumn("Opponent", width="small"),
            "Fantasy Points": st.column_config.NumberColumn(
                "Fantasy Points", format="%.2f", width="small"
            ),
        },
        hide_index=True,
        height=650,
        width="stretch",
    )
