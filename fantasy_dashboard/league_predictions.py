from dataclasses import dataclass, replace
from functools import cache
from math import ceil, log2
from random import Random
from statistics import NormalDist
from typing import Any

from fantasy_dashboard.models.draft import DraftPickModel
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


@dataclass(frozen=True, slots=True)
class DraftTeamProjection:
    user_id: str
    weekly_mean: float
    weekly_standard_deviation: float
    average_weekly_win_probability: float
    playoff_probability: float
    championship_probability: float
    championship_grade_score: float


POSITION_WEEKLY_CV = {
    "QB": 0.45,
    "RB": 0.59,
    "WR": 0.64,
    "TE": 0.67,
    "K": 0.55,
    "DEF": 1.02,
}
DEFAULT_WEEKLY_CV = 0.50
NFL_GAMES_PER_TEAM = 17


def championship_grade_score(
    championship_probability: float,
    team_count: int,
) -> float:
    """Map title odds to a conventional grade using equal-share odds as a C."""
    if team_count <= 0:
        return 0.0
    fair_share_probability = 1 / team_count
    score = 50 + 25 * championship_probability / fair_share_probability
    return min(100.0, max(0.0, score))


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


def _draft_roster(
    user_id: str,
    roster_id: int,
    player_ids: list[str],
    league_id: str,
) -> RosterModel:
    return RosterModel(
        starters=[],
        wins=0,
        waiver=0,
        budget_used=0,
        moves=0,
        ties=0,
        losses=0,
        points=0,
        points_against=0,
        roster_id=roster_id,
        reserve=[],
        players=player_ids,
        user_id=user_id,
        league_id=league_id,
    )


def _lineup_distribution(
    roster: RosterModel,
    league: LeagueModel,
    players: dict[str, dict[str, Any]],
    projected_stats: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    lineup = optimize_lineup(roster, league, players, projected_stats)
    variance = 0.0
    weekly_mean = 0.0
    for player_id in lineup.player_ids:
        if player_id is None:
            continue
        season_points = calculate_fantasy_points(
            projected_stats.get(player_id, {}), league.scoring_settings
        )
        player_mean = max(0.0, season_points / NFL_GAMES_PER_TEAM)
        position = str(players.get(player_id, {}).get("position") or "")
        player_deviation = max(
            1.0, player_mean * POSITION_WEEKLY_CV.get(position, DEFAULT_WEEKLY_CV)
        )
        weekly_mean += player_mean
        variance += player_deviation**2
    return weekly_mean, variance**0.5


def _average_weekly_win_probability(
    user_id: str,
    distributions: dict[str, tuple[float, float]],
) -> float:
    mean, deviation = distributions[user_id]
    probabilities = []
    for opponent_id, (opponent_mean, opponent_deviation) in distributions.items():
        if opponent_id == user_id:
            continue
        difference_deviation = (deviation**2 + opponent_deviation**2) ** 0.5
        if difference_deviation <= 0:
            probabilities.append(0.5)
        else:
            probabilities.append(
                NormalDist().cdf((mean - opponent_mean) / difference_deviation)
            )
    return sum(probabilities) / len(probabilities) if probabilities else 1.0


def _round_robin_pairs(user_ids: list[str], week: int) -> list[tuple[str, str]]:
    participants: list[str | None] = [*user_ids]
    if len(participants) % 2:
        participants.append(None)
    if len(participants) < 2:
        return []
    rotations = week % (len(participants) - 1)
    for _ in range(rotations):
        participants = [
            participants[0],
            participants[-1],
            *participants[1:-1],
        ]
    pairs = []
    for index in range(len(participants) // 2):
        left = participants[index]
        right = participants[-1 - index]
        if left is not None and right is not None:
            pairs.append((left, right))
    return pairs


def project_draft_championship_odds(
    league: LeagueModel,
    picks: list[DraftPickModel],
    teams: list[SleeperTeam],
    players: dict[str, dict[str, Any]],
    projected_stats: dict[str, dict[str, Any]],
    *,
    simulations: int = 5000,
    random_seed: int = 2026,
) -> dict[str, DraftTeamProjection]:
    """Simulate season and playoff outcomes for the originally drafted rosters."""
    player_ids_by_user: dict[str, list[str]] = {}
    for pick in picks:
        if pick.picked_by:
            player_ids_by_user.setdefault(pick.picked_by, []).append(pick.player_id)
    drafting_user_ids = [
        team.user_id for team in teams if player_ids_by_user.get(team.user_id)
    ]
    if not drafting_user_ids:
        return {}

    distributions = {}
    for roster_id, user_id in enumerate(drafting_user_ids, 1):
        distributions[user_id] = _lineup_distribution(
            _draft_roster(
                user_id,
                roster_id,
                player_ids_by_user[user_id],
                league.league_id,
            ),
            league,
            players,
            projected_stats,
        )

    simulation_count = max(1, int(simulations))
    playoff_team_count = min(league.settings.playoff_teams, len(drafting_user_ids))
    playoff_counts = {user_id: 0 for user_id in drafting_user_ids}
    championship_counts = {user_id: 0 for user_id in drafting_user_ids}
    rng = Random(random_seed)

    def score(user_id: str) -> float:
        mean, deviation = distributions[user_id]
        return max(0.0, rng.gauss(mean, deviation))

    regular_season_weeks = max(1, league.settings.playoff_start_week - 1)
    for _ in range(simulation_count):
        wins = {user_id: 0 for user_id in drafting_user_ids}
        points = {user_id: 0.0 for user_id in drafting_user_ids}
        for week in range(regular_season_weeks):
            for left_id, right_id in _round_robin_pairs(drafting_user_ids, week):
                left_score = score(left_id)
                right_score = score(right_id)
                points[left_id] += left_score
                points[right_id] += right_score
                if left_score == right_score:
                    winner_id = rng.choice((left_id, right_id))
                else:
                    winner_id = left_id if left_score > right_score else right_id
                wins[winner_id] += 1

        seeded = sorted(
            drafting_user_ids,
            key=lambda user_id: (-wins[user_id], -points[user_id], user_id),
        )[:playoff_team_count]
        for user_id in seeded:
            playoff_counts[user_id] += 1

        if not seeded:
            continue
        if len(seeded) == 1:
            championship_counts[seeded[0]] += 1
            continue
        entrants_by_seed = {seed: user_id for seed, user_id in enumerate(seeded, 1)}
        bracket_size = 2 ** ceil(log2(len(seeded)))
        slots: list[str | None] = [
            entrants_by_seed.get(seed) for seed in _seed_order(bracket_size)
        ]
        while len(slots) > 1:
            next_slots: list[str | None] = []
            for index in range(0, len(slots), 2):
                left_id, right_id = slots[index : index + 2]
                if left_id is None:
                    winner_id = right_id
                elif right_id is None:
                    winner_id = left_id
                else:
                    left_score = score(left_id)
                    right_score = score(right_id)
                    if left_score == right_score:
                        winner_id = rng.choice((left_id, right_id))
                    else:
                        winner_id = left_id if left_score > right_score else right_id
                next_slots.append(winner_id)
            slots = next_slots
        if slots[0] is not None:
            championship_counts[slots[0]] += 1

    championship_probabilities = {
        user_id: championship_counts[user_id] / simulation_count
        for user_id in drafting_user_ids
    }
    return {
        user_id: DraftTeamProjection(
            user_id=user_id,
            weekly_mean=round(distributions[user_id][0], 2),
            weekly_standard_deviation=round(distributions[user_id][1], 2),
            average_weekly_win_probability=round(
                _average_weekly_win_probability(user_id, distributions), 4
            ),
            playoff_probability=round(playoff_counts[user_id] / simulation_count, 4),
            championship_probability=round(championship_probabilities[user_id], 4),
            championship_grade_score=round(
                championship_grade_score(
                    championship_probabilities[user_id], len(drafting_user_ids)
                ),
                2,
            ),
        )
        for user_id in drafting_user_ids
    }


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
