from numbers import Real
from typing import Any

from fantasy_dashboard.models.league import RosterModel

FLEX_POSITIONS = {
    "FLEX": {"RB", "WR", "TE"},
    "REC_FLEX": {"WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "IDP_FLEX": {"DB", "DL", "LB"},
}

POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"]

COMMON_STATS = [("Games", "gp")]
POSITION_STATS = {
    "QB": [
        ("Pass Att", "pass_att"),
        ("Completions", "pass_cmp"),
        ("Pass Yds", "pass_yd"),
        ("Pass TD", "pass_td"),
        ("Pass INT", "pass_int"),
        ("Rush Yds", "rush_yd"),
        ("Rush TD", "rush_td"),
    ],
    "RB": [
        ("Carries", "rush_att"),
        ("Rush Yds", "rush_yd"),
        ("Rush TD", "rush_td"),
        ("Targets", "rec_tgt"),
        ("Receptions", "rec"),
        ("Rec Yds", "rec_yd"),
        ("Rec TD", "rec_td"),
    ],
    "WR": [
        ("Targets", "rec_tgt"),
        ("Receptions", "rec"),
        ("Rec Yds", "rec_yd"),
        ("Rec TD", "rec_td"),
        ("Rush Yds", "rush_yd"),
        ("Rush TD", "rush_td"),
    ],
    "TE": [
        ("Targets", "rec_tgt"),
        ("Receptions", "rec"),
        ("Rec Yds", "rec_yd"),
        ("Rec TD", "rec_td"),
    ],
    "K": [
        ("FG Att", "fga"),
        ("FG Made", "fgm"),
        ("XP Att", "xpa"),
        ("XP Made", "xpm"),
    ],
    "DEF": [
        ("Sacks", "sack"),
        ("Def INT", "int"),
        ("Fum Rec", "fum_rec"),
        ("Def TD", "def_td"),
        ("Pts Allowed", "pts_allow"),
        ("Yds Allowed", "yds_allow"),
    ],
    "DL": [
        ("Tackles", "tkl"),
        ("Solo Tkl", "tkl_solo"),
        ("Tkl Loss", "tkl_loss"),
        ("Sacks", "sack"),
        ("QB Hits", "qb_hit"),
    ],
    "LB": [
        ("Tackles", "tkl"),
        ("Solo Tkl", "tkl_solo"),
        ("Tkl Loss", "tkl_loss"),
        ("Sacks", "sack"),
        ("Def INT", "int"),
    ],
    "DB": [
        ("Tackles", "tkl"),
        ("Solo Tkl", "tkl_solo"),
        ("Pass Def", "pass_def"),
        ("Def INT", "int"),
        ("Def TD", "def_td"),
    ],
}

ALL_STATS = list(
    dict.fromkeys(
        [*COMMON_STATS, *(stat for stats in POSITION_STATS.values() for stat in stats)]
    )
)


# Expand league flex slots into the concrete positions users can filter by.
def get_rosterable_positions(roster_positions: list[str]) -> list[str]:
    positions: set[str] = set()
    for roster_position in roster_positions:
        if roster_position in {"BN", "IR", "TAXI"}:
            continue
        if roster_position in FLEX_POSITIONS:
            positions.update(FLEX_POSITIONS[roster_position])
        else:
            positions.add(roster_position)

    ordered = [position for position in POSITION_ORDER if position in positions]
    return ordered + sorted(positions.difference(ordered))


# Apply the active league's scoring multipliers to Sleeper's raw stat totals.
def calculate_fantasy_points(
    stats: dict[str, Any], scoring_settings: dict[str, Any]
) -> float:
    points = 0.0
    for stat_name, multiplier in scoring_settings.items():
        stat_value = stats.get(stat_name)
        if isinstance(stat_value, Real) and isinstance(multiplier, Real):
            points += float(stat_value) * float(multiplier)
    return round(points, 2)


# Identify the stat columns worth emphasizing for one player's position.
def get_relevant_stat_labels(position: str) -> set[str]:
    return {
        "Fantasy Points",
        *(label for label, _ in COMMON_STATS + POSITION_STATS.get(position, [])),
    }


def _display_position(
    player_data: dict[str, Any], rosterable_positions: set[str]
) -> str:
    fantasy_positions = player_data.get("fantasy_positions") or []
    return next(
        (
            str(position)
            for position in fantasy_positions
            if position in rosterable_positions
        ),
        str(player_data.get("position") or ""),
    )


# Join current availability, player identity, and selected-period statistics.
def build_player_stat_rows(
    players: dict[str, dict[str, Any]],
    rosters: list[RosterModel],
    stats_by_player_id: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
    rosterable_positions: list[str],
    selected_position: str | None = None,
    available_only: bool = False,
) -> list[dict[str, Any]]:
    rostered_player_ids = {
        str(player_id)
        for roster in rosters
        for player_id in roster.players
        if player_id is not None
    }
    allowed_positions = set(rosterable_positions)
    rows: list[dict[str, Any]] = []

    for player_id, player_data in players.items():
        position = _display_position(player_data, allowed_positions)
        if position not in allowed_positions:
            continue
        if selected_position is not None and position != selected_position:
            continue
        if not player_data.get("active"):
            continue
        if not player_data.get("team") and position != "DEF":
            continue

        is_available = str(player_id) not in rostered_player_ids
        if available_only and not is_available:
            continue

        player_stats = stats_by_player_id.get(str(player_id), {})
        player_name = (
            f"{player_data.get('first_name') or ''} "
            f"{player_data.get('last_name') or ''}"
        ).strip()
        rows.append(
            {
                "Player": player_name or str(player_id),
                "Position": position,
                "Team": str(player_data.get("team") or "FA"),
                "Availability": "Available" if is_available else "Rostered",
                "Fantasy Points": calculate_fantasy_points(
                    player_stats, scoring_settings
                ),
                **{
                    label: player_stats.get(stat_name, 0) or 0
                    for label, stat_name in ALL_STATS
                },
            }
        )

    return sorted(
        rows,
        key=lambda row: (-row["Fantasy Points"], row["Player"]),
    )
