from typing import Any


# Resolve Sleeper trend results against the shared player metadata cache.
def build_player_trend_rows(
    trends: list[dict[str, int | str]],
    players: dict[str, dict[str, Any]],
    count_label: str,
    roster_labels_by_player_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trend in trends:
        player_id = str(trend["player_id"])
        player = players.get(player_id, {})
        player_name = (
            f"{player.get('first_name') or ''} {player.get('last_name') or ''}"
        ).strip()
        rows.append(
            {
                "Player": player_name or player_id,
                **(
                    {"Roster": roster_labels_by_player_id.get(player_id, "")}
                    if roster_labels_by_player_id is not None
                    else {}
                ),
                "Position": str(player.get("position") or "—"),
                "Team": str(player.get("team") or "FA"),
                count_label: int(trend["count"]),
            }
        )
    return rows
