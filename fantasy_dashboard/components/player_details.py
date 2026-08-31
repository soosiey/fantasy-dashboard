from typing import Any

import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.data import get_player_weekly_stats
from fantasy_dashboard.player_stats import (
    ALL_STATS,
    build_player_stat_row,
    build_player_weekly_stat_rows,
    format_stat_table_for_display,
    get_relevant_stat_labels,
)


def render_player_stats_table(
    weekly_table: pd.DataFrame,
    position: str,
    *,
    table_height: int = 650,
    relevant_only: bool = False,
    show_stat_filter: bool = False,
    filter_key: str = "player-stats-view",
) -> None:
    """Render the shared weekly table for both dialogs and full pages."""
    stat_view = "Relevant Stats" if relevant_only else "All Stats"
    if show_stat_filter:
        stat_view = (
            st.segmented_control(
                "Stats shown",
                ["All Stats", "Relevant Stats"],
                default="All Stats",
                key=filter_key,
                width="content",
            )
            or "All Stats"
        )

    relevant_columns = get_relevant_stat_labels(position)
    if stat_view == "Relevant Stats":
        context_columns = {"Week", "Opponent"}
        weekly_table = weekly_table[
            [
                column
                for column in weekly_table.columns
                if column in context_columns or column in relevant_columns
            ]
        ]

    if "Opponent" in weekly_table.columns:
        weekly_table = weekly_table[
            [
                "Week",
                "Opponent",
                *(
                    column
                    for column in weekly_table.columns
                    if column not in {"Week", "Opponent"}
                ),
            ]
        ]

    def highlight_relevant_stats(row: pd.Series) -> list[str]:
        return [
            (
                "background-color: rgba(59, 130, 246, 0.10)"
                if column in relevant_columns
                else ""
            )
            for column in row.index
        ]

    weekly_table = format_stat_table_for_display(weekly_table)
    st.dataframe(
        weekly_table.style.apply(highlight_relevant_stats, axis=1),
        column_config={
            **{
                label: st.column_config.TextColumn(
                    label,
                    width="small",
                )
                for label, _ in ALL_STATS
            },
            "Week": st.column_config.NumberColumn("Week", width="small"),
            "Opponent": st.column_config.TextColumn("Opponent", width="small"),
            "Fantasy Points": st.column_config.TextColumn(
                "Fantasy Points", width="small"
            ),
        },
        hide_index=True,
        height=table_height,
        width="stretch",
    )


# Render player identity and an 18-week, league-scored game log in any container.
def render_player_details(
    player_id: str,
    player: dict[str, Any],
    season: str,
    season_type: str,
    scoring_settings: dict[str, Any],
    *,
    selected_stats: dict[str, Any] | None = None,
    selected_week: int | None = None,
    stats_source: str | None = None,
    show_news_button: bool = False,
    show_stat_filter: bool = False,
) -> None:
    player_name = (
        f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
    ).strip()
    position = str(player.get("position") or "—")
    team = str(player.get("team") or "FA")
    number = player.get("number")

    if show_news_button:
        name_column, news_column = st.columns([3, 1], vertical_alignment="center")
        with name_column:
            st.header(player_name or player_id)
        with news_column:
            if st.button(
                "View Recent News",
                key=f"player-details-news-{player_id}",
                width="stretch",
            ):
                st.session_state["matchups_news_player_id"] = player_id
                st.rerun(scope="app")
    else:
        st.header(player_name or player_id)
    details = [team, position]
    if number not in (None, ""):
        details.append(f"#{number}")
    st.caption(" · ".join(details))

    # Matchup dialogs use the selected week's already-loaded source, while the
    # player browser retains its full actual-stat game log.
    if selected_stats is not None and selected_week is not None:
        st.caption(f"{stats_source or 'Statistics'} · Week {selected_week}")
        weekly_table = pd.DataFrame(
            [
                build_player_stat_row(
                    selected_stats,
                    scoring_settings,
                    selected_week,
                )
            ]
        )
        table_height = 150
    else:
        try:
            with st.spinner("Loading weekly statistics..."):
                weekly_stats = get_player_weekly_stats(player_id, season, season_type)
        except (requests.RequestException, TypeError, ValueError):
            st.warning("Weekly player statistics could not be loaded.")
            return

        weekly_table = pd.DataFrame(
            build_player_weekly_stat_rows(weekly_stats, scoring_settings)
        )
        table_height = 650

    render_player_stats_table(
        weekly_table,
        position,
        table_height=table_height,
        show_stat_filter=show_stat_filter,
        filter_key=f"player-details-stat-view-{player_id}-{selected_week}",
    )


# Keep the overview and matchup interaction as a modal around the shared content.
@st.dialog("Player Details", width="large")
def show_player_details(
    player_id: str,
    player: dict[str, Any],
    season: str,
    season_type: str,
    scoring_settings: dict[str, Any],
    *,
    selected_stats: dict[str, Any] | None = None,
    selected_week: int | None = None,
    stats_source: str | None = None,
    show_news_button: bool = False,
    show_stat_filter: bool = False,
) -> None:
    render_player_details(
        player_id,
        player,
        season,
        season_type,
        scoring_settings,
        selected_stats=selected_stats,
        selected_week=selected_week,
        stats_source=stats_source,
        show_news_button=show_news_button,
        show_stat_filter=show_stat_filter,
    )
