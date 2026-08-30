from collections.abc import Iterable

import pandas as pd
import streamlit as st

COMPARISON_COLUMN = "Add to comparison"


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
) -> None:
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
    st.session_state[selection_key] = sorted(selected_player_ids)
