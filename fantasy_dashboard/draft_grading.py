from collections import Counter
from dataclasses import dataclass
from functools import cache
from math import ceil
from typing import Any

from fantasy_dashboard.models.draft import DraftPickModel
from fantasy_dashboard.models.league import LeagueModel
from fantasy_dashboard.player_stats import FLEX_POSITIONS, calculate_fantasy_points

NON_STARTING_SLOTS = {"BN", "IR", "TAXI"}


@dataclass(frozen=True, slots=True)
class DraftGradeWeights:
    strength: float = 0.4
    roster_fit: float = 0.6
    cost: float = 0.25
    bench_depth: float = 0.10
    wait_cost: float = 0.05


@dataclass(frozen=True, slots=True)
class DraftPickGrade:
    score: float
    letter: str
    strength_score: float
    roster_fit_score: float
    projected_points: float
    position_average: float
    marginal_roster_value: float
    best_available_roster_value: float
    wait_cost: float
    cost_score: float | None
    fair_value: float | None
    amount_paid: float | None


def letter_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _primary_position(player: dict[str, Any]) -> str:
    return str(player.get("position") or "")


def _eligible_positions(player: dict[str, Any]) -> set[str]:
    fantasy_positions = player.get("fantasy_positions")
    if isinstance(fantasy_positions, list):
        positions = {str(position) for position in fantasy_positions if position}
        if positions:
            return positions
    position = _primary_position(player)
    return {position} if position else set()


def position_replacement_levels(
    league: LeagueModel,
    points: dict[str, float],
    players: dict[str, dict[str, Any]],
) -> dict[str, float]:
    demand_per_team: Counter[str] = Counter()
    for slot in league.roster_positions:
        if slot in NON_STARTING_SLOTS:
            continue
        eligible = FLEX_POSITIONS.get(str(slot), {str(slot)})
        share = 1 / len(eligible)
        for position in eligible:
            demand_per_team[position] += share

    values_by_position: dict[str, list[float]] = {}
    for player_id, value in points.items():
        position = _primary_position(players.get(player_id, {}))
        if position:
            values_by_position.setdefault(position, []).append(value)

    replacements: dict[str, float] = {}
    for position, values in values_by_position.items():
        values.sort(reverse=True)
        demand = max(1, ceil(league.settings.num_teams * demand_per_team[position]))
        replacements[position] = values[min(demand - 1, len(values) - 1)]
    return replacements


def roster_utility(
    player_ids: tuple[str, ...],
    league: LeagueModel,
    points: dict[str, float],
    players: dict[str, dict[str, Any]],
    replacements: dict[str, float],
    bench_depth_weight: float,
) -> float:
    slots = tuple(
        str(slot) for slot in league.roster_positions if slot not in NON_STARTING_SLOTS
    )
    eligible_by_player = {
        player_id: _eligible_positions(players.get(player_id, {}))
        for player_id in player_ids
    }

    @cache
    def best_lineup(
        player_index: int, filled_slots: int
    ) -> tuple[float, tuple[str, ...]]:
        if player_index == len(player_ids):
            return 0.0, ()
        player_id = player_ids[player_index]
        best_value, best_starters = best_lineup(player_index + 1, filled_slots)
        position = _primary_position(players.get(player_id, {}))
        value_over_replacement = max(
            0.0, points.get(player_id, 0.0) - replacements.get(position, 0.0)
        )
        for slot_index, slot in enumerate(slots):
            bit = 1 << slot_index
            slot_positions = FLEX_POSITIONS.get(slot, {slot})
            if filled_slots & bit or not eligible_by_player[player_id].intersection(
                slot_positions
            ):
                continue
            candidate_value, candidate_starters = best_lineup(
                player_index + 1, filled_slots | bit
            )
            candidate_value += value_over_replacement
            if candidate_value > best_value:
                best_value = candidate_value
                best_starters = (player_id, *candidate_starters)
        return best_value, best_starters

    starter_value, starter_ids = best_lineup(0, 0)
    starter_set = set(starter_ids)
    bench_by_position: dict[str, list[float]] = {}
    for player_id in player_ids:
        if player_id in starter_set:
            continue
        position = _primary_position(players.get(player_id, {}))
        surplus = max(0.0, points.get(player_id, 0.0) - replacements.get(position, 0.0))
        if surplus:
            bench_by_position.setdefault(position, []).append(surplus)

    bench_value = 0.0
    for surpluses in bench_by_position.values():
        for depth_rank, surplus in enumerate(sorted(surpluses, reverse=True), 1):
            bench_value += surplus / depth_rank
    return starter_value + bench_depth_weight * bench_value


def _filled_starting_slots(
    player_ids: tuple[str, ...],
    league: LeagueModel,
    players: dict[str, dict[str, Any]],
) -> int:
    slots = tuple(
        str(slot) for slot in league.roster_positions if slot not in NON_STARTING_SLOTS
    )

    @cache
    def maximum(player_index: int, filled_slots: int) -> int:
        if player_index == len(player_ids):
            return filled_slots.bit_count()
        player_positions = _eligible_positions(
            players.get(player_ids[player_index], {})
        )
        best = maximum(player_index + 1, filled_slots)
        for slot_index, slot in enumerate(slots):
            bit = 1 << slot_index
            if filled_slots & bit or not player_positions.intersection(
                FLEX_POSITIONS.get(slot, {slot})
            ):
                continue
            best = max(best, maximum(player_index + 1, filled_slots | bit))
        return best

    return maximum(0, 0)


def _position_percentile(
    player_id: str,
    position: str,
    points: dict[str, float],
    players: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    comparison_values = [
        value
        for other_id, value in points.items()
        if other_id != player_id
        and _primary_position(players.get(other_id, {})) == position
    ]
    if not comparison_values:
        return (100.0 if player_id in points else 0.0), 0.0
    player_points = points.get(player_id, 0.0)
    percentile = (
        100
        * sum(value <= player_points for value in comparison_values)
        / len(comparison_values)
    )
    return min(100.0, percentile), sum(comparison_values) / len(comparison_values)


def _next_pick_index(picks: list[DraftPickModel], index: int) -> int | None:
    user_id = picks[index].picked_by
    return next(
        (
            next_index
            for next_index in range(index + 1, len(picks))
            if picks[next_index].picked_by == user_id
        ),
        None,
    )


def _auction_fair_value(
    player_id: str,
    index: int,
    picks: list[DraftPickModel],
    available_ids: set[str],
    points: dict[str, float],
    players: dict[str, dict[str, Any]],
    replacements: dict[str, float],
) -> float | None:
    remaining_picks = [pick for pick in picks[index:] if pick.amount is not None]
    if not remaining_picks:
        return None

    # Revalue the remaining player pool against the dollars that the market still
    # has to spend. This captures auction inflation or deflation after every bid.
    minimum_bid = 1.0
    remaining_spend = sum(max(0.0, pick.amount or 0.0) for pick in remaining_picks)
    discretionary_dollars = max(
        0.0, remaining_spend - minimum_bid * len(remaining_picks)
    )
    surplus_by_player = {
        candidate_id: max(
            0.0,
            points.get(candidate_id, 0.0)
            - replacements.get(_primary_position(players.get(candidate_id, {})), 0.0),
        )
        for candidate_id in available_ids | {player_id}
    }
    draftable_players = sorted(
        surplus_by_player,
        key=surplus_by_player.get,
        reverse=True,
    )[: len(remaining_picks)]
    remaining_surplus = sum(
        surplus_by_player[candidate_id] for candidate_id in draftable_players
    )
    player_surplus = surplus_by_player.get(player_id, 0.0)
    if (
        remaining_surplus <= 0
        or player_surplus <= 0
        or player_id not in draftable_players
    ):
        return minimum_bid
    return minimum_bid + discretionary_dollars * player_surplus / remaining_surplus


def _auction_cost_score(amount_paid: float, fair_value: float) -> float:
    if amount_paid <= fair_value or amount_paid <= 0:
        return 100.0
    return 100.0 * fair_value / amount_paid


def grade_draft_picks(
    league: LeagueModel,
    picks: list[DraftPickModel],
    players: dict[str, dict[str, Any]],
    projected_stats: dict[str, dict[str, Any]],
    weights: DraftGradeWeights,
) -> dict[int, DraftPickGrade]:
    points = {
        player_id: calculate_fantasy_points(stats, league.scoring_settings)
        for player_id, stats in projected_stats.items()
        if player_id in players
    }
    replacements = position_replacement_levels(league, points, players)
    available_ids = set(points)
    drafted_by_user: dict[str, list[str]] = {}
    grades: dict[int, DraftPickGrade] = {}

    for index, pick in enumerate(picks):
        roster_ids = tuple(drafted_by_user.get(pick.picked_by, []))
        base_utility = roster_utility(
            roster_ids,
            league,
            points,
            players,
            replacements,
            weights.bench_depth,
        )
        position = _primary_position(players.get(pick.player_id, {}))
        strength_score, position_average = _position_percentile(
            pick.player_id, position, points, players
        )

        next_index = _next_pick_index(picks, index)
        removed_before_next = (
            {future_pick.player_id for future_pick in picks[index + 1 : next_index]}
            if next_index is not None
            else set()
        )
        positions = {
            _primary_position(players.get(player_id, {})) for player_id in available_ids
        }
        wait_costs: dict[str, float] = {}
        for candidate_position in positions:
            if next_index is None:
                wait_costs[candidate_position] = 0.0
                continue
            current_values = [
                points[player_id]
                for player_id in available_ids
                if _primary_position(players.get(player_id, {})) == candidate_position
            ]
            later_values = [
                points[player_id]
                for player_id in available_ids - removed_before_next - {pick.player_id}
                if _primary_position(players.get(player_id, {})) == candidate_position
            ]
            best_now = max(
                current_values, default=replacements.get(candidate_position, 0)
            )
            best_later = max(
                later_values, default=replacements.get(candidate_position, 0)
            )
            wait_costs[candidate_position] = max(0.0, best_now - best_later)

        best_by_position: dict[str, str] = {}
        for player_id in available_ids | {pick.player_id}:
            player_position = _primary_position(players.get(player_id, {}))
            current_best = best_by_position.get(player_position)
            if current_best is None or points.get(player_id, 0) > points.get(
                current_best, 0
            ):
                best_by_position[player_position] = player_id
        candidate_ids = set(best_by_position.values()) | {pick.player_id}
        candidate_values: dict[str, float] = {}
        remaining_team_picks = sum(
            future_pick.picked_by == pick.picked_by
            for future_pick in picks[index + 1 :]
        )
        starting_slot_count = sum(
            slot not in NON_STARTING_SLOTS for slot in league.roster_positions
        )
        for candidate_id in candidate_ids:
            filled_slots = _filled_starting_slots(
                (*roster_ids, candidate_id), league, players
            )
            if starting_slot_count - filled_slots > remaining_team_picks:
                candidate_values[candidate_id] = 0.0
                continue
            candidate_utility = roster_utility(
                (*roster_ids, candidate_id),
                league,
                points,
                players,
                replacements,
                weights.bench_depth,
            )
            candidate_position = _primary_position(players.get(candidate_id, {}))
            candidate_values[candidate_id] = max(
                0.0, candidate_utility - base_utility
            ) + (weights.wait_cost * wait_costs.get(candidate_position, 0.0))

        actual_value = candidate_values.get(pick.player_id, 0.0)
        best_value = max(candidate_values.values(), default=0.0)
        roster_fit_score = 100.0 if best_value <= 0 else 100 * actual_value / best_value
        fair_value = (
            _auction_fair_value(
                pick.player_id,
                index,
                picks,
                available_ids,
                points,
                players,
                replacements,
            )
            if pick.amount is not None
            else None
        )
        cost_score = (
            _auction_cost_score(pick.amount, fair_value)
            if pick.amount is not None and fair_value is not None
            else None
        )
        score_weight_total = weights.strength + weights.roster_fit
        weighted_score = (
            weights.strength * strength_score + weights.roster_fit * roster_fit_score
        )
        if cost_score is not None:
            score_weight_total += weights.cost
            weighted_score += weights.cost * cost_score
        overall_score = (
            weighted_score / score_weight_total if score_weight_total > 0 else 0.0
        )
        grades[pick.pick_number] = DraftPickGrade(
            score=round(overall_score, 2),
            letter=letter_grade(overall_score),
            strength_score=round(strength_score, 2),
            roster_fit_score=round(roster_fit_score, 2),
            projected_points=round(points.get(pick.player_id, 0.0), 2),
            position_average=round(position_average, 2),
            marginal_roster_value=round(actual_value, 2),
            best_available_roster_value=round(best_value, 2),
            wait_cost=round(wait_costs.get(position, 0.0), 2),
            cost_score=round(cost_score, 2) if cost_score is not None else None,
            fair_value=round(fair_value, 2) if fair_value is not None else None,
            amount_paid=pick.amount,
        )
        drafted_by_user.setdefault(pick.picked_by, []).append(pick.player_id)
        available_ids.discard(pick.player_id)

    return grades
