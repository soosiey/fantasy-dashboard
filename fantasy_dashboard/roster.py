from typing import Any

from fantasy_dashboard.models.league import LeagueModel, RosterModel
from fantasy_dashboard.models.player import PlayerModel

# Positions managed separately from the starting lineup.
NON_STARTING_POSITIONS = {"BN", "IR"}


def get_roster_player_order(roster: RosterModel) -> list[str]:
    """Return lineup players in starter, bench, then reserve order."""
    starters = [
        str(player_id) for player_id in roster.starters if player_id not in (None, "0")
    ]
    starter_ids = set(starters)
    reserves = [
        str(player_id) for player_id in roster.reserve if player_id not in (None, "0")
    ]
    reserve_ids = set(reserves)
    players = [
        str(player_id) for player_id in roster.players if player_id not in (None, "0")
    ]
    bench = [
        player_id
        for player_id in players
        if player_id not in starter_ids and player_id not in reserve_ids
    ]
    return list(dict.fromkeys([*starters, *bench, *reserves]))


# Resolve one cached JSON record into the application's player model.
def _get_player(
    players: dict[str, dict[str, Any]], player_id: str | None
) -> PlayerModel | None:
    if not player_id or player_id == "0":
        return None

    player_json = players.get(player_id)
    if player_json is None:
        return None
    return PlayerModel.from_json(player_json)


# Produce a readable name while retaining useful fallbacks for missing records.
def _get_player_name(player: PlayerModel | None, player_id: str | None) -> str:
    if player is None:
        return player_id if player_id and player_id != "0" else "Empty"

    full_name = f"{player.first_name} {player.last_name}".strip()
    return full_name or player.player_id


# Shape one player into the values expected by the roster table.
def _get_roster_row(
    roster_position: str,
    players: dict[str, dict[str, Any]],
    player_id: str | None,
    show_player_position: bool = False,
) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    player = _get_player(players, player_id)
    player_position = player.position if player and player.position else None
    injury_status = player.injury_status if player and player.injury_status else None
    player_team = player.team if player and player.team else None
    resolved_player_id = player.player_id if player else None
    return (
        roster_position,
        _get_player_name(player, player_id),
        player_position if show_player_position else None,
        injury_status,
        player_team,
        resolved_player_id,
    )


def build_roster_rows(
    league: LeagueModel,
    roster: RosterModel,
    players: dict[str, dict[str, Any]],
) -> list[tuple[str, str, str | None, str | None, str | None, str | None]]:
    # Pair configured starting slots with the roster's ordered starter IDs.
    starter_positions = [
        position
        for position in league.roster_positions
        if position not in NON_STARTING_POSITIONS
    ]
    rows = [
        _get_roster_row(
            position.replace("_", " "),
            players,
            roster.starters[index] if index < len(roster.starters) else None,
        )
        for index, position in enumerate(starter_positions)
    ]

    # Fill configured bench slots with every non-starting, non-reserve player.
    starter_ids = set(roster.starters)
    reserve_ids = set(roster.reserve)
    bench_ids = [
        player_id
        for player_id in roster.players
        if player_id not in starter_ids and player_id not in reserve_ids
    ]
    bench_slots = max(league.roster_positions.count("BN"), len(bench_ids))
    rows.extend(
        _get_roster_row(
            "BN",
            players,
            bench_ids[index] if index < len(bench_ids) else None,
            show_player_position=True,
        )
        for index in range(bench_slots)
    )

    # Append injured-reserve slots and leave unoccupied slots visibly empty.
    reserve_slots = max(league.settings.reserves, len(roster.reserve))
    rows.extend(
        _get_roster_row(
            "IR",
            players,
            roster.reserve[index] if index < len(roster.reserve) else None,
            show_player_position=True,
        )
        for index in range(reserve_slots)
    )
    return rows


# Find the full player model selected by a roster action.
def get_player_by_id(
    players: dict[str, dict[str, Any]], player_id: str
) -> PlayerModel | None:
    return _get_player(players, player_id)
