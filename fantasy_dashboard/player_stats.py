from html import escape
from math import trunc
from numbers import Real
from typing import Any
from urllib.parse import quote

from fantasy_dashboard.models.league import RosterModel
from fantasy_dashboard.models.user import SleeperTeam

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
        ("FG Made 0–19", "fgm_0_19"),
        ("FG Made 20–29", "fgm_20_29"),
        ("FG Made 30–39", "fgm_30_39"),
        ("FG Made 40–49", "fgm_40_49"),
        ("FG Made 50–59", "fgm_50_59"),
        ("FG Made 60+", "fgm_60p"),
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


# Limit displayed statistics without rounding projected fractional values upward.
def truncate_decimal(value: Any, decimal_places: int = 2) -> float:
    numeric_value = float(value) if isinstance(value, Real) else 0.0
    scale = 10**decimal_places
    return trunc(numeric_value * scale) / scale


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
    return truncate_decimal(points)


# Return the shared, ordered stat fields relevant to one or more positions.
def get_relevant_stat_fields(
    *positions: str,
) -> list[tuple[str, str | None]]:
    relevant_labels = {
        label
        for position in positions
        for label, _ in POSITION_STATS.get(position, [])
    }
    return [
        ("Fantasy Points", None),
        *COMMON_STATS,
        *(stat for stat in ALL_STATS if stat[0] in relevant_labels),
    ]


# Identify the stat columns worth emphasizing for one player's position.
def get_relevant_stat_labels(position: str) -> set[str]:
    return {label for label, _ in get_relevant_stat_fields(position)}


# Describe each rostered player using the owner's Sleeper display name.
def build_player_roster_labels(
    rosters: list[RosterModel], teams: list[SleeperTeam]
) -> dict[str, str]:
    teams_by_user_id = {team.user_id: team for team in teams}
    labels: dict[str, str] = {}
    for roster in rosters:
        team = teams_by_user_id.get(roster.user_id)
        if team is None:
            continue
        label = team.display_name
        labels.update(
            {
                str(player_id): label
                for player_id in roster.players
                if player_id is not None
            }
        )
    return labels


# Render a player and optional owner as one image-backed dataframe cell so each
# text fragment can retain its own size and color inside Streamlit's data grid.
def build_player_identity_image(player_name: str, owner_name: str = "") -> str:
    player_center = 105
    approximate_player_half_width = len(player_name) * 3.9
    owner = (
        f'<text class="owner" x="{player_center + approximate_player_half_width + 6}" '
        f'y="19">· {escape(owner_name)}</text>'
        if owner_name
        else ""
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="260" height="28">
<style>
.player {{ fill: #6366f1; font: 600 14px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
.owner {{ fill: #808495; font-size: 11px; }}
@media (prefers-color-scheme: dark) {{
  .owner {{ fill: #9ca3af; }}
}}
</style>
<text class="player" x="{player_center}" y="19" text-anchor="middle">{escape(player_name)}</text>
{owner}
</svg>"""
    return f"data:image/svg+xml;utf8,{quote(svg, safe='')}"


# Shape one selected week's stats using the same columns as the player browser.
def build_player_stat_row(
    stats: dict[str, Any],
    scoring_settings: dict[str, Any],
    week: int,
) -> dict[str, Any]:
    return {
        "Week": week,
        "Fantasy Points": calculate_fantasy_points(stats, scoring_settings),
        **{
            label: truncate_decimal(stats.get(stat_name, 0) or 0)
            for label, stat_name in ALL_STATS
        },
    }


# Shape an 18-week player game log using the same stat columns as the browser.
def build_player_weekly_stat_rows(
    weekly_stats: dict[int, dict[str, Any]],
    scoring_settings: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for week in range(1, 19):
        record = weekly_stats.get(week, {})
        stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
        opponent = str(record.get("opponent") or "—")
        if opponent != "—":
            opponent = f"@ {opponent}" if record.get("is_away_team") else f"vs {opponent}"
        row = build_player_stat_row(stats, scoring_settings, week)
        row["Opponent"] = opponent
        rows.append(row)
    return rows


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
    roster_labels_by_player_id: dict[str, str] | None = None,
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
                "Player ID": str(player_id),
                "Player": player_name or str(player_id),
                **(
                    {
                        "Roster": roster_labels_by_player_id.get(
                            str(player_id), ""
                        )
                    }
                    if roster_labels_by_player_id is not None
                    else {}
                ),
                "Position": position,
                "Team": str(player_data.get("team") or "FA"),
                "Availability": "Available" if is_available else "Rostered",
                "Fantasy Points": truncate_decimal(
                    calculate_fantasy_points(player_stats, scoring_settings)
                ),
                **{
                    label: truncate_decimal(
                        player_stats.get(stat_name, 0) or 0
                    )
                    for label, stat_name in ALL_STATS
                },
            }
        )

    return sorted(
        rows,
        key=lambda row: (-row["Fantasy Points"], row["Player"]),
    )
