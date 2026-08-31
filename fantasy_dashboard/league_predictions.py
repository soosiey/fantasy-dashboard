from dataclasses import dataclass, replace
from functools import cache
from math import ceil, log2
from typing import Any

from fantasy_dashboard.models.league import LeagueModel, RosterModel
from fantasy_dashboard.models.matchup import WeeklyMatchupModel
from fantasy_dashboard.models.user import SleeperTeam
from fantasy_dashboard.player_stats import FLEX_POSITIONS, calculate_fantasy_points
from fantasy_dashboard.playoffs import PlayoffMatchup, PlayoffSlot

NON_STARTING_SLOTS = {"BN", "IR", "TAXI"}


@dataclass(frozen=True, slots=True)
class OptimalLineup:
    score: float
    player_ids: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class ProjectedStanding:
    roster_id: int
    team_name: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    seed: int = 0


@dataclass(frozen=True, slots=True)
class PlayoffProjection:
    rounds: dict[int, list[PlayoffMatchup]]
    champion: ProjectedStanding | None
    runner_up: ProjectedStanding | None


def _eligible_positions(player: dict[str, Any]) -> set[str]:
    fantasy_positions = player.get("fantasy_positions")
    if isinstance(fantasy_positions, list):
        positions = {str(position) for position in fantasy_positions if position}
        if positions:
            return positions
    position = str(player.get("position") or "")
    return {position} if position else set()


def _can_fill(slot: str, positions: set[str]) -> bool:
    return bool(positions.intersection(FLEX_POSITIONS.get(slot, {slot})))


def optimize_lineup(
    roster: RosterModel,
    league: LeagueModel,
    players: dict[str, dict[str, Any]],
    stats_by_player_id: dict[str, dict[str, Any]],
) -> OptimalLineup:
    """Assign the highest projected legal combination to the starting slots."""
    slots = tuple(
        str(position)
        for position in league.roster_positions
        if position not in NON_STARTING_SLOTS
    )
    rostered_players = tuple(
        dict.fromkeys(
            str(player_id)
            for player_id in roster.players
            if player_id not in (None, "0") and str(player_id) in players
        )
    )
    positions_by_player = {
        player_id: _eligible_positions(players[player_id])
        for player_id in rostered_players
    }
    points_by_player = {
        player_id: calculate_fantasy_points(
            stats_by_player_id.get(player_id, {}), league.scoring_settings
        )
        for player_id in rostered_players
    }

    @cache
    def best_assignment(
        player_index: int, filled_slots: int
    ) -> tuple[int, float, tuple[str | None, ...]]:
        if player_index == len(rostered_players):
            return 0, 0.0, (None,) * len(slots)

        player_id = rostered_players[player_index]
        best_count, best_score, best_players = best_assignment(
            player_index + 1, filled_slots
        )
        for slot_index, slot in enumerate(slots):
            slot_bit = 1 << slot_index
            if filled_slots & slot_bit or not _can_fill(
                slot, positions_by_player[player_id]
            ):
                continue
            candidate_count, candidate_score, candidate_players = best_assignment(
                player_index + 1, filled_slots | slot_bit
            )
            candidate_count += 1
            candidate_score += points_by_player[player_id]
            if (candidate_count, candidate_score) > (best_count, best_score):
                best_count = candidate_count
                best_score = candidate_score
                best_players = (
                    *candidate_players[:slot_index],
                    player_id,
                    *candidate_players[slot_index + 1 :],
                )
        return best_count, best_score, best_players

    _, score, player_ids = best_assignment(0, 0)
    return OptimalLineup(score=round(score, 2), player_ids=player_ids)


def build_optimized_week_matchups(
    league: LeagueModel,
    rosters: list[RosterModel],
    players: dict[str, dict[str, Any]],
    weekly_matchups: list[WeeklyMatchupModel],
    projections_by_player_id: dict[str, dict[str, Any]],
) -> list[WeeklyMatchupModel]:
    """Replace submitted starters with each current roster's optimal lineup."""
    rosters_by_id = {roster.roster_id: roster for roster in rosters}
    optimized_matchups: list[WeeklyMatchupModel] = []
    for matchup in weekly_matchups:
        roster = rosters_by_id.get(matchup.roster_id)
        if roster is None:
            continue
        lineup = optimize_lineup(roster, league, players, projections_by_player_id)
        optimized_matchups.append(
            WeeklyMatchupModel(
                starters=[player_id or "0" for player_id in lineup.player_ids],
                players=[
                    str(player_id)
                    for player_id in roster.players
                    if player_id not in (None, "0")
                ],
                roster_id=roster.roster_id,
                matchup_id=matchup.matchup_id,
                points=lineup.score,
                custom_points=None,
            )
        )
    return optimized_matchups


def _rank(standings: list[ProjectedStanding]) -> list[ProjectedStanding]:
    ranked = sorted(
        standings,
        key=lambda standing: (
            -standing.wins,
            -standing.points_for,
            -standing.points_against,
            standing.roster_id,
        ),
    )
    return [replace(standing, seed=seed) for seed, standing in enumerate(ranked, 1)]


def project_regular_season(
    league: LeagueModel,
    rosters: list[RosterModel],
    teams: list[SleeperTeam],
    players: dict[str, dict[str, Any]],
    matchups_by_week: dict[int, list[WeeklyMatchupModel]],
    projections_by_week: dict[int, dict[str, dict[str, Any]]],
) -> list[ProjectedStanding]:
    """Add optimized outcomes for the supplied remaining weeks to current records."""
    teams_by_user_id = {team.user_id: team for team in teams}
    rosters_by_id = {roster.roster_id: roster for roster in rosters}
    standings = {
        roster.roster_id: ProjectedStanding(
            roster_id=roster.roster_id,
            team_name=(
                teams_by_user_id[roster.user_id].display_team_name
                if roster.user_id in teams_by_user_id
                else f"Roster {roster.roster_id}"
            ),
            wins=roster.wins,
            losses=roster.losses,
            ties=roster.ties,
            points_for=roster.points,
            points_against=roster.points_against,
        )
        for roster in rosters
    }

    for week, weekly_matchups in sorted(matchups_by_week.items()):
        weekly_scores = {
            roster_id: optimize_lineup(
                roster,
                league,
                players,
                projections_by_week.get(week, {}),
            ).score
            for roster_id, roster in rosters_by_id.items()
        }
        grouped: dict[int, list[int]] = {}
        for matchup in weekly_matchups:
            if matchup.roster_id not in standings:
                continue
            group_id = (
                matchup.matchup_id
                if matchup.matchup_id is not None
                else -matchup.roster_id
            )
            grouped.setdefault(group_id, []).append(matchup.roster_id)

        for roster_ids in grouped.values():
            if len(roster_ids) != 2:
                continue
            left_id, right_id = roster_ids
            left_score = weekly_scores[left_id]
            right_score = weekly_scores[right_id]
            left = standings[left_id]
            right = standings[right_id]
            if left_score == right_score:
                left_result = (0, 0, 1)
                right_result = (0, 0, 1)
            elif left_score > right_score:
                left_result = (1, 0, 0)
                right_result = (0, 1, 0)
            else:
                left_result = (0, 1, 0)
                right_result = (1, 0, 0)
            standings[left_id] = replace(
                left,
                wins=left.wins + left_result[0],
                losses=left.losses + left_result[1],
                ties=left.ties + left_result[2],
                points_for=round(left.points_for + left_score, 2),
                points_against=round(left.points_against + right_score, 2),
            )
            standings[right_id] = replace(
                right,
                wins=right.wins + right_result[0],
                losses=right.losses + right_result[1],
                ties=right.ties + right_result[2],
                points_for=round(right.points_for + right_score, 2),
                points_against=round(right.points_against + left_score, 2),
            )

    return _rank(list(standings.values()))


def _seed_order(bracket_size: int) -> list[int]:
    order = [1, 2]
    size = 2
    while size < bracket_size:
        size *= 2
        order = [seed for current in order for seed in (current, size + 1 - current)]
    return order


def project_playoffs(
    league: LeagueModel,
    rosters: list[RosterModel],
    standings: list[ProjectedStanding],
    players: dict[str, dict[str, Any]],
    projections_by_week: dict[int, dict[str, dict[str, Any]]],
) -> PlayoffProjection:
    playoff_team_count = min(league.settings.playoff_teams, len(standings))
    if playoff_team_count < 2:
        return PlayoffProjection(rounds={}, champion=None, runner_up=None)

    entrants = standings[:playoff_team_count]
    entrants_by_seed = {standing.seed: standing for standing in entrants}
    rosters_by_id = {roster.roster_id: roster for roster in rosters}
    bracket_size = 2 ** ceil(log2(playoff_team_count))
    slots: list[ProjectedStanding | None] = [
        entrants_by_seed.get(seed) for seed in _seed_order(bracket_size)
    ]
    rounds: dict[int, list[PlayoffMatchup]] = {}
    runner_up: ProjectedStanding | None = None
    round_number = 1
    matchup_id = 1

    while len(slots) > 1:
        week = league.settings.playoff_start_week + round_number - 1
        week_projections = projections_by_week.get(week, {})
        next_slots: list[ProjectedStanding | None] = []
        round_matchups: list[PlayoffMatchup] = []
        for index in range(0, len(slots), 2):
            team_1, team_2 = slots[index : index + 2]
            if team_1 is not None and team_2 is not None:
                score_1 = optimize_lineup(
                    rosters_by_id[team_1.roster_id], league, players, week_projections
                ).score
                score_2 = optimize_lineup(
                    rosters_by_id[team_2.roster_id], league, players, week_projections
                ).score
            else:
                score_1 = None
                score_2 = None
            if team_1 is None:
                winner, loser = team_2, None
            elif team_2 is None:
                winner, loser = team_1, None
            elif score_1 > score_2 or (
                score_1 == score_2 and team_1.seed < team_2.seed
            ):
                winner, loser = team_1, team_2
            else:
                winner, loser = team_2, team_1
            next_slots.append(winner)
            if len(slots) == 2:
                runner_up = loser

            round_matchups.append(
                PlayoffMatchup(
                    matchup_id=matchup_id,
                    title="Championship" if len(slots) == 2 else f"Match {matchup_id}",
                    team_1=PlayoffSlot(
                        label=team_1.team_name if team_1 else "Bye week",
                        roster_id=team_1.roster_id if team_1 else None,
                        is_winner=team_1 is not None and team_1 == winner,
                        seed=team_1.seed if team_1 else None,
                        score=score_1,
                    ),
                    team_2=PlayoffSlot(
                        label=team_2.team_name if team_2 else "Bye week",
                        roster_id=team_2.roster_id if team_2 else None,
                        is_winner=team_2 is not None and team_2 == winner,
                        seed=team_2.seed if team_2 else None,
                        score=score_2,
                    ),
                )
            )
            matchup_id += 1
        rounds[round_number] = round_matchups
        slots = next_slots
        round_number += 1

    return PlayoffProjection(
        rounds=rounds,
        champion=slots[0],
        runner_up=runner_up,
    )
