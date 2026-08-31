import pandas as pd

from fantasy_dashboard.components import comparison_selection
from fantasy_dashboard.components.comparison_selection import (
    COMPARISON_COLUMN,
    MAX_COMPARISON_PLAYERS,
    cap_comparison_player_ids,
    save_comparison_selection,
)


def test_comparison_player_ids_are_unique_and_capped_at_five() -> None:
    player_ids, was_capped = cap_comparison_player_ids(
        ["one", "two", "one", "three", "four", "five", "six"]
    )

    assert player_ids == ["one", "two", "three", "four", "five"]
    assert len(player_ids) == MAX_COMPARISON_PLAYERS
    assert was_capped is True


def test_sixth_selection_is_rejected_and_resets_editor(
    monkeypatch,
) -> None:
    session_state: dict[str, object] = {}
    monkeypatch.setattr(comparison_selection.st, "session_state", session_state)
    edited_table = pd.DataFrame(
        {
            "Player ID": [str(index) for index in range(6)],
            COMPARISON_COLUMN: [True] * 6,
        }
    )

    should_rerun = save_comparison_selection(
        edited_table,
        edited_table["Player ID"],
        "league-1",
        editor_key_base="players-table",
    )

    assert should_rerun is True
    assert session_state["comparison-player-ids-league-1"] == [
        "0",
        "1",
        "2",
        "3",
        "4",
    ]
    assert session_state["comparison-player-limit-warning-league-1"] is True
    assert session_state["comparison-editor-version-players-table-league-1"] == 1
