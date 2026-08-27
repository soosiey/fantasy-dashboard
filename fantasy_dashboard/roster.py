from typing import Any

from fantasy_dashboard.models.league import LeagueModel, RosterModel

NON_STARTING_POSITIONS = {"BN", "IR"}


def get_player_name(players: dict[str, dict[str, Any]], player_id: str | None) -> str:
    if not player_id or player_id == "0":
        return "Empty"

    player = players.get(player_id)
    if player is None:
        return player_id

    full_name = player.get("full_name")
    if full_name:
        return full_name

    name_parts = (player.get("first_name"), player.get("last_name"))
    return " ".join(part for part in name_parts if part) or player_id


def get_player_position(
    players: dict[str, dict[str, Any]], player_id: str | None
) -> str | None:
    if not player_id or player_id == "0":
        return None

    player = players.get(player_id)
    if player is None or not player.get("position"):
        return None
    return str(player["position"])


def build_roster_rows(
    league: LeagueModel,
    roster: RosterModel,
    players: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str | None]]:
    starter_positions = [
        position
        for position in league.roster_positions
        if position not in NON_STARTING_POSITIONS
    ]
    rows = [
        (
            position.replace("_", " "),
            get_player_name(
                players,
                roster.starters[index] if index < len(roster.starters) else None,
            ),
            None,
        )
        for index, position in enumerate(starter_positions)
    ]

    starter_ids = set(roster.starters)
    reserve_ids = set(roster.reserve)
    bench_ids = [
        player_id
        for player_id in roster.players
        if player_id not in starter_ids and player_id not in reserve_ids
    ]
    bench_slots = max(league.roster_positions.count("BN"), len(bench_ids))
    rows.extend(
        (
            "BN",
            get_player_name(
                players, bench_ids[index] if index < len(bench_ids) else None
            ),
            get_player_position(
                players, bench_ids[index] if index < len(bench_ids) else None
            ),
        )
        for index in range(bench_slots)
    )

    reserve_slots = max(league.settings.reserves, len(roster.reserve))
    rows.extend(
        (
            "IR",
            get_player_name(
                players,
                roster.reserve[index] if index < len(roster.reserve) else None,
            ),
            get_player_position(
                players,
                roster.reserve[index] if index < len(roster.reserve) else None,
            ),
        )
        for index in range(reserve_slots)
    )
    return rows
