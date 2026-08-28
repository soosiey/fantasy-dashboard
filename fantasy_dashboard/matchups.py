from dataclasses import dataclass
from typing import Any

from fantasy_dashboard.models.league import LeagueModel, RosterModel
from fantasy_dashboard.models.matchup import WeeklyMatchupModel
from fantasy_dashboard.models.player import PlayerModel
from fantasy_dashboard.models.user import SleeperTeam
from fantasy_dashboard.player_stats import calculate_fantasy_points

POSITION_LABELS = {
    "SUPER_FLEX": "SFLEX",
    "REC_FLEX": "FLEX",
    "WRRB_FLEX": "FLEX",
}


# Store the compact player identity shown on either side of a matchup.
@dataclass(frozen=True, slots=True)
class MatchupPlayer:
    name: str
    nfl_team: str
    opponent: str = ""
    points: float = 0
    player_id: str | None = None
    injury_status: str | None = None
    game_status: str = ""
    is_inactive: bool = False


# Store one team's placard information for a weekly matchup.
@dataclass(frozen=True, slots=True)
class MatchupTeam:
    team_name: str
    display_name: str
    points: float
    user_id: str | None
    to_play_count: int = 0


# Pair two starting players around their shared fantasy position.
@dataclass(frozen=True, slots=True)
class MatchupLineupRow:
    position: str
    left_player: MatchupPlayer
    right_player: MatchupPlayer


# Represent one complete head-to-head matchup ready for display.
@dataclass(frozen=True, slots=True)
class HeadToHeadMatchup:
    left_team: MatchupTeam
    right_team: MatchupTeam
    lineup: list[MatchupLineupRow]


# Resolve a player ID from the shared Sleeper player cache.
def _get_matchup_player(
    players: dict[str, dict[str, Any]],
    player_id: str | None,
    player_points: dict[str, float] | None = None,
    opponents_by_team: dict[str, str] | None = None,
    game_statuses_by_team: dict[str, str] | None = None,
) -> MatchupPlayer:
    if not player_id or player_id == "0" or player_id not in players:
        return MatchupPlayer(name="Empty", nfl_team="")

    player_data = players[player_id]
    player = PlayerModel.from_json(player_data)
    player_name = f"{player.first_name} {player.last_name}".strip()
    player_status = str(player_data.get("status") or "").strip().casefold()
    return MatchupPlayer(
        name=player_name or player.player_id,
        nfl_team=player.team,
        opponent=(opponents_by_team or {}).get(player.team, ""),
        points=(player_points or {}).get(player_id, 0),
        player_id=player_id,
        injury_status=player.injury_status or None,
        game_status=(game_statuses_by_team or {}).get(player.team, ""),
        is_inactive=(
            player_data.get("active") is False
            or player_status in {"inactive", "ineligible"}
        ),
    )


# Build each NFL team's selected-week opponent label with home/away context.
def build_week_opponents(schedule: list[dict[str, Any]], week: int) -> dict[str, str]:
    opponents: dict[str, str] = {}
    for game in schedule:
        if game.get("week") != week:
            continue
        home = str(game.get("home") or "").strip().upper()
        away = str(game.get("away") or "").strip().upper()
        if home and away:
            opponents[home] = f"vs {away}"
            opponents[away] = f"at {home}"
    return opponents


# Convert Sleeper's weekly game state into the three matchup display states.
def build_week_game_statuses(
    schedule: list[dict[str, Any]], week: int
) -> dict[str, str]:
    status_aliases = {
        "pre_game": "to-play",
        "scheduled": "to-play",
        "pre": "to-play",
        "in_game": "playing",
        "in_progress": "playing",
        "live": "playing",
        "post_game": "finished",
        "complete": "finished",
        "completed": "finished",
        "final": "finished",
        "closed": "finished",
    }
    statuses: dict[str, str] = {}
    for game in schedule:
        if game.get("week") != week:
            continue
        display_status = status_aliases.get(
            str(game.get("status") or "").strip().casefold()
        )
        if display_status is None:
            continue
        for team_field in ("home", "away"):
            team = str(game.get(team_field) or "").strip().upper()
            if team:
                statuses[team] = display_status
    return statuses


# Match a weekly roster entry to its league team identity and score.
def _get_matchup_team(
    matchup: WeeklyMatchupModel | None,
    rosters_by_id: dict[int, RosterModel],
    teams_by_user_id: dict[str, SleeperTeam],
    starter_points: float | None = None,
    to_play_count: int = 0,
) -> MatchupTeam:
    if matchup is None:
        return MatchupTeam(team_name="Bye", display_name="", points=0, user_id=None)

    roster = rosters_by_id.get(matchup.roster_id)
    team = teams_by_user_id.get(roster.user_id) if roster is not None else None
    return MatchupTeam(
        team_name=team.display_team_name
        if team is not None
        else f"Roster {matchup.roster_id}",
        display_name=team.display_name if team is not None else "",
        points=(matchup.displayed_points if starter_points is None else starter_points),
        user_id=team.user_id if team is not None else None,
        to_play_count=to_play_count,
    )


# Calculate this week's player scores from raw NFL stats and league rules.
def _get_player_points(
    matchup: WeeklyMatchupModel | None,
    stats_by_player_id: dict[str, dict[str, Any]] | None,
    scoring_settings: dict[str, Any],
) -> dict[str, float]:
    if matchup is None:
        return {}
    if stats_by_player_id is None:
        return matchup.players_points

    player_ids = set(matchup.players) | set(matchup.starters)
    return {
        player_id: calculate_fantasy_points(
            stats_by_player_id.get(player_id, {}), scoring_settings
        )
        for player_id in player_ids
        if player_id and player_id != "0"
    }


# Build mirrored starter rows for every head-to-head pairing in the selected week.
def build_head_to_head_matchups(
    weekly_matchups: list[WeeklyMatchupModel],
    league: LeagueModel,
    rosters: list[RosterModel],
    teams: list[SleeperTeam],
    players: dict[str, dict[str, Any]],
    stats_by_player_id: dict[str, dict[str, Any]] | None = None,
    opponents_by_team: dict[str, str] | None = None,
    game_statuses_by_team: dict[str, str] | None = None,
) -> list[HeadToHeadMatchup]:
    rosters_by_id = {roster.roster_id: roster for roster in rosters}
    teams_by_user_id = {team.user_id: team for team in teams}
    starting_positions = [
        position for position in league.roster_positions if position not in {"BN", "IR"}
    ]

    grouped_matchups: dict[int, list[WeeklyMatchupModel]] = {}
    for matchup in weekly_matchups:
        group_id = (
            matchup.matchup_id if matchup.matchup_id is not None else -matchup.roster_id
        )
        grouped_matchups.setdefault(group_id, []).append(matchup)

    head_to_head_matchups: list[HeadToHeadMatchup] = []
    for _, matchup_teams in sorted(grouped_matchups.items()):
        matchup_teams.sort(key=lambda matchup: matchup.roster_id)
        left_matchup = matchup_teams[0]
        right_matchup = matchup_teams[1] if len(matchup_teams) > 1 else None
        left_player_points = _get_player_points(
            left_matchup, stats_by_player_id, league.scoring_settings
        )
        right_player_points = _get_player_points(
            right_matchup, stats_by_player_id, league.scoring_settings
        )
        lineup = [
            MatchupLineupRow(
                position=POSITION_LABELS.get(position, position.replace("_", "")),
                left_player=_get_matchup_player(
                    players,
                    (
                        left_matchup.starters[index]
                        if index < len(left_matchup.starters)
                        else None
                    ),
                    left_player_points,
                    opponents_by_team,
                    game_statuses_by_team,
                ),
                right_player=_get_matchup_player(
                    players,
                    (
                        right_matchup.starters[index]
                        if right_matchup is not None
                        and index < len(right_matchup.starters)
                        else None
                    ),
                    right_player_points,
                    opponents_by_team,
                    game_statuses_by_team,
                ),
            )
            for index, position in enumerate(starting_positions)
        ]

        # Pair active bench players beneath the starters without including reserves.
        left_roster = rosters_by_id.get(left_matchup.roster_id)
        right_roster = (
            rosters_by_id.get(right_matchup.roster_id)
            if right_matchup is not None
            else None
        )
        left_reserve_ids = set(left_roster.reserve if left_roster is not None else [])
        right_reserve_ids = set(
            right_roster.reserve if right_roster is not None else []
        )
        left_starter_ids = set(left_matchup.starters)
        right_starter_ids = set(right_matchup.starters if right_matchup else [])
        left_bench_ids = [
            player_id
            for player_id in left_matchup.players
            if player_id not in left_starter_ids and player_id not in left_reserve_ids
        ]
        right_bench_ids = [
            player_id
            for player_id in (right_matchup.players if right_matchup else [])
            if player_id not in right_starter_ids and player_id not in right_reserve_ids
        ]
        bench_slots = max(
            league.roster_positions.count("BN"),
            len(left_bench_ids),
            len(right_bench_ids),
        )
        lineup.extend(
            MatchupLineupRow(
                position="BN",
                left_player=_get_matchup_player(
                    players,
                    left_bench_ids[index] if index < len(left_bench_ids) else None,
                    left_player_points,
                    opponents_by_team,
                    game_statuses_by_team,
                ),
                right_player=_get_matchup_player(
                    players,
                    right_bench_ids[index] if index < len(right_bench_ids) else None,
                    right_player_points,
                    opponents_by_team,
                    game_statuses_by_team,
                ),
            )
            for index in range(bench_slots)
        )
        head_to_head_matchups.append(
            HeadToHeadMatchup(
                left_team=_get_matchup_team(
                    left_matchup,
                    rosters_by_id,
                    teams_by_user_id,
                    sum(
                        row.left_player.points for row in lineup if row.position != "BN"
                    ),
                    sum(
                        row.left_player.game_status == "to-play"
                        for row in lineup
                        if row.position != "BN"
                    ),
                ),
                right_team=_get_matchup_team(
                    right_matchup,
                    rosters_by_id,
                    teams_by_user_id,
                    sum(
                        row.right_player.points
                        for row in lineup
                        if row.position != "BN"
                    ),
                    sum(
                        row.right_player.game_status == "to-play"
                        for row in lineup
                        if row.position != "BN"
                    ),
                ),
                lineup=lineup,
            )
        )
    return head_to_head_matchups
