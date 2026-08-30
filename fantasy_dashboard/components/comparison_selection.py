from collections.abc import Iterable
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

COMPARISON_COLUMN = "Add to comparison"


def render_comparison_column_label() -> None:
    """Place a readable label above the intentionally blank checkbox header."""
    st.markdown(
        """
        <div style="color: #808495; font-size: 0.8rem; font-weight: 600;
                    text-align: center; width: 7rem;">
            Comparison
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_comparison_column(
    table: pd.DataFrame,
    player_ids: Iterable[str],
    league_id: str,
) -> pd.DataFrame:
    """Preselect players already chosen elsewhere in this league's analysis."""
    selection_key = f"comparison-player-ids-{league_id}"
    selected_player_ids = {
        str(player_id) for player_id in st.session_state.get(selection_key, [])
    }
    table.insert(
        0,
        COMPARISON_COLUMN,
        [str(player_id) in selected_player_ids for player_id in player_ids],
    )
    return table


def save_comparison_selection(
    edited_table: pd.DataFrame,
    visible_player_ids: Iterable[str],
    league_id: str,
) -> bool:
    """Merge the current table's checkboxes with selections from other views."""
    selection_key = f"comparison-player-ids-{league_id}"
    selected_player_ids = {
        str(player_id) for player_id in st.session_state.get(selection_key, [])
    }
    visible_ids = {str(player_id) for player_id in visible_player_ids}
    selected_player_ids.difference_update(visible_ids)
    selected_player_ids.update(
        edited_table.loc[edited_table[COMPARISON_COLUMN], "Player ID"].astype(str)
    )
    updated_player_ids = sorted(selected_player_ids)
    selection_changed = updated_player_ids != sorted(
        str(player_id) for player_id in st.session_state.get(selection_key, [])
    )
    st.session_state[selection_key] = updated_player_ids
    return selection_changed


def render_comparison_sidebar(
    players: dict[str, dict[str, Any]],
    league_id: str,
) -> None:
    """Show selected players in a fixed drawer on every analysis page."""
    selection_key = f"comparison-player-ids-{league_id}"
    selected_player_ids = [
        str(player_id) for player_id in st.session_state.get(selection_key, [])
    ]
    selected_players = [
        players[player_id] for player_id in selected_player_ids if player_id in players
    ]
    if not selected_players:
        return

    st.markdown(
        """
        <style>
            @media (min-width: 1100px) {
                [data-testid="stMainBlockContainer"]:has(
                    [class*="st-key-comparison-drawer"]
                ) {
                    padding-right: 20rem;
                }
                [class*="st-key-comparison-drawer"] {
                    background: var(--secondary-background-color);
                    border: 1px solid rgba(128, 128, 128, 0.25);
                    border-radius: 0.75rem;
                    box-shadow: 0 0.5rem 1.5rem rgba(0, 0, 0, 0.12);
                    max-height: calc(100vh - 6rem);
                    overflow-y: auto;
                    padding: 1rem;
                    position: fixed;
                    right: 1.5rem;
                    top: 4.5rem;
                    width: 17rem;
                    z-index: 999;
                }
            }
            .comparison-player {
                border-top: 1px solid rgba(128, 128, 128, 0.2);
                padding: 0.7rem 0;
            }
            .comparison-player-name {
                font-weight: 600;
            }
            .comparison-player-meta {
                color: #808495;
                font-size: 0.78rem;
                margin-top: 0.1rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="comparison-drawer"):
        st.subheader("Comparison")
        for player in selected_players:
            player_name = (
                f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
            ).strip()
            position = str(player.get("position") or "—")
            team = str(player.get("team") or "FA")
            st.markdown(
                '<div class="comparison-player">'
                f'<div class="comparison-player-name">{escape(player_name)}</div>'
                f'<div class="comparison-player-meta">{escape(position)} · '
                f"{escape(team)}</div></div>",
                unsafe_allow_html=True,
            )
