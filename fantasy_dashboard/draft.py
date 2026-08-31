from dataclasses import dataclass
from typing import Any

from fantasy_dashboard.models.draft import DraftPickModel


# Hold the display-ready values used by the draft results table.
@dataclass(frozen=True, slots=True)
class DraftResultRow:
    pick_number: int
    round_number: int
    player_name: str
    drafted_by: str
    amount: float | None


# Join draft picks to the current player catalog, retaining API name fallbacks.
def build_draft_result_rows(
    picks: list[DraftPickModel],
    players: dict[str, dict[str, Any]],
    display_names_by_user_id: dict[str, str] | None = None,
    search_query: str = "",
    drafted_by_user_id: str = "",
) -> list[DraftResultRow]:
    normalized_query = search_query.strip().casefold()
    display_names_by_user_id = display_names_by_user_id or {}
    rows: list[DraftResultRow] = []

    for pick in picks:
        if drafted_by_user_id and pick.picked_by != drafted_by_user_id:
            continue
        player = players.get(pick.player_id) or {}
        catalog_name = " ".join(
            part
            for part in (
                str(player.get("first_name") or "").strip(),
                str(player.get("last_name") or "").strip(),
            )
            if part
        )
        player_name = catalog_name or pick.player_name or "Unknown Player"
        if normalized_query and normalized_query not in player_name.casefold():
            continue
        rows.append(
            DraftResultRow(
                pick_number=pick.pick_number,
                round_number=pick.round_number,
                player_name=player_name,
                drafted_by=display_names_by_user_id.get(pick.picked_by, "Unknown User"),
                amount=pick.amount,
            )
        )

    return rows
