from dataclasses import dataclass
from typing import Any

from fantasy_dashboard.draft_grading import (
    letter_grade,
    position_replacement_levels,
    roster_utility,
)
from fantasy_dashboard.models.league import LeagueModel
from fantasy_dashboard.player_stats import calculate_fantasy_points


@dataclass(frozen=True, slots=True)
class TradeGradeWeights:
    strength: float = 0.5
    roster_fit: float = 0.5
    bench_depth: float = 0.35


@dataclass(frozen=True, slots=True)
class TradeSideGrade:
    score: float
    letter: str
    strength_score: float
    roster_fit_score: float
    sent_projected_points: float
    received_projected_points: float
    sent_value_over_replacement: float
    received_value_over_replacement: float
    before_roster_utility: float
    after_roster_utility: float
    roster_utility_change: float
    sent_utility: float
    received_utility: float
    sent_utilization: float
    received_utilization: float


@dataclass(frozen=True, slots=True)
class HypotheticalTradeGrade:
    first: TradeSideGrade
    second: TradeSideGrade


def _primary_position(player: dict[str, Any]) -> str:
    return str(player.get("position") or "")


def _bounded(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _package_value(
    player_ids: tuple[str, ...],
    points: dict[str, float],
    players: dict[str, dict[str, Any]],
    replacements: dict[str, float],
) -> float:
    return sum(
        max(
            0.0,
            points.get(player_id, 0.0)
            - replacements.get(_primary_position(players.get(player_id, {})), 0.0),
        )
        for player_id in player_ids
    )


def _trade_component_score(advantage: float) -> float:
    """Map an advantage in [-1, 1] to a conventional-grade score in [50, 100]."""
    return 75.0 + 25.0 * _bounded(advantage, -1.0, 1.0)


def _grade_trade_side(
    roster_ids: tuple[str, ...],
    sent_ids: tuple[str, ...],
    received_ids: tuple[str, ...],
    league: LeagueModel,
    points: dict[str, float],
    players: dict[str, dict[str, Any]],
    replacements: dict[str, float],
    weights: TradeGradeWeights,
) -> TradeSideGrade:
    roster_set = set(roster_ids)
    sent_ids = tuple(
        dict.fromkeys(
            player_id for player_id in sent_ids if player_id in roster_set
        )
    )
    received_ids = tuple(dict.fromkeys(received_ids))
    remaining_ids = tuple(
        player_id for player_id in roster_ids if player_id not in sent_ids
    )
    after_ids = tuple(dict.fromkeys((*remaining_ids, *received_ids)))

    before_utility = roster_utility(
        roster_ids,
        league,
        points,
        players,
        replacements,
        weights.bench_depth,
    )
    remaining_utility = roster_utility(
        remaining_ids,
        league,
        points,
        players,
        replacements,
        weights.bench_depth,
    )
    after_utility = roster_utility(
        after_ids,
        league,
        points,
        players,
        replacements,
        weights.bench_depth,
    )

    sent_value = _package_value(sent_ids, points, players, replacements)
    received_value = _package_value(received_ids, points, players, replacements)
    total_value = sent_value + received_value
    strength_advantage = (
        (received_value - sent_value) / total_value if total_value > 0 else 0.0
    )
    strength_score = _trade_component_score(strength_advantage)

    sent_utility = max(0.0, before_utility - remaining_utility)
    received_utility = max(0.0, after_utility - remaining_utility)
    sent_utilization = (
        _bounded(sent_utility / sent_value, 0.0, 1.0) if sent_value > 0 else 0.0
    )
    received_utilization = (
        _bounded(received_utility / received_value, 0.0, 1.0)
        if received_value > 0
        else 0.0
    )
    roster_fit_score = _trade_component_score(
        received_utilization - sent_utilization
    )

    weight_total = weights.strength + weights.roster_fit
    overall_score = (
        (
            weights.strength * strength_score
            + weights.roster_fit * roster_fit_score
        )
        / weight_total
        if weight_total > 0
        else 75.0
    )
    sent_projected_points = sum(points.get(player_id, 0.0) for player_id in sent_ids)
    received_projected_points = sum(
        points.get(player_id, 0.0) for player_id in received_ids
    )
    return TradeSideGrade(
        score=round(overall_score, 2),
        letter=letter_grade(overall_score),
        strength_score=round(strength_score, 2),
        roster_fit_score=round(roster_fit_score, 2),
        sent_projected_points=round(sent_projected_points, 2),
        received_projected_points=round(received_projected_points, 2),
        sent_value_over_replacement=round(sent_value, 2),
        received_value_over_replacement=round(received_value, 2),
        before_roster_utility=round(before_utility, 2),
        after_roster_utility=round(after_utility, 2),
        roster_utility_change=round(after_utility - before_utility, 2),
        sent_utility=round(sent_utility, 2),
        received_utility=round(received_utility, 2),
        sent_utilization=round(sent_utilization, 4),
        received_utilization=round(received_utilization, 4),
    )


def grade_hypothetical_trade(
    league: LeagueModel,
    first_roster_ids: list[str],
    second_roster_ids: list[str],
    first_sends: list[str],
    second_sends: list[str],
    players: dict[str, dict[str, Any]],
    projected_stats: dict[str, dict[str, Any]],
    weights: TradeGradeWeights | None = None,
) -> HypotheticalTradeGrade:
    """Grade both sides of a proposed two-team, player-only trade."""
    weights = weights or TradeGradeWeights()
    points = {
        player_id: calculate_fantasy_points(stats, league.scoring_settings)
        for player_id, stats in projected_stats.items()
        if player_id in players
    }
    replacements = position_replacement_levels(league, points, players)
    first_roster = tuple(
        dict.fromkeys(str(player_id) for player_id in first_roster_ids)
    )
    second_roster = tuple(
        dict.fromkeys(str(player_id) for player_id in second_roster_ids)
    )
    first_sent = tuple(dict.fromkeys(str(player_id) for player_id in first_sends))
    second_sent = tuple(dict.fromkeys(str(player_id) for player_id in second_sends))

    return HypotheticalTradeGrade(
        first=_grade_trade_side(
            first_roster,
            first_sent,
            second_sent,
            league,
            points,
            players,
            replacements,
            weights,
        ),
        second=_grade_trade_side(
            second_roster,
            second_sent,
            first_sent,
            league,
            points,
            players,
            replacements,
            weights,
        ),
    )
