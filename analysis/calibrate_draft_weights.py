#!/usr/bin/env python3
"""Calibrate draft-pick scoring weights from completed Sleeper seasons.

The script deliberately separates two outcomes:
1. points a pick actually contributed in the drafting team's starters; and
2. marginal points in that team's optimal draft-only lineup.

It selects bench-depth and tier-drop settings by leave-one-team-season-out
validation, estimates non-negative strength/fit/cost coefficients, and then
stabilizes the small-sample estimates into defaults suitable for the UI.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fantasy_dashboard.clients.espn import EspnClient, map_projections_to_sleeper
from fantasy_dashboard.draft_grading import DraftGradeWeights, grade_draft_picks
from fantasy_dashboard.league_predictions import optimize_lineup
from fantasy_dashboard.models.draft import DraftPickModel
from fantasy_dashboard.models.league import LeagueModel, RosterModel

SLEEPER_API = "https://api.sleeper.app/v1"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


class JsonCache:
    def __init__(self, root: Path, refresh: bool = False) -> None:
        self.root = root
        self.refresh = refresh
        root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, url: str) -> Any:
        path = self.root / f"{key}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = response.json()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data


@dataclass(slots=True)
class LeagueRun:
    season: int
    league_id: str
    draft_type: str
    league: LeagueModel
    picks: list[DraftPickModel]
    raw_picks: list[dict[str, Any]]
    projections: dict[str, dict[str, float]]


@dataclass(slots=True)
class Observation:
    season: int
    league_id: str
    pick: int
    user: str
    roster_id: int
    position: str
    draft_type: str
    deployed: float
    optimal: float


def parse_league(value: str) -> tuple[int, str]:
    try:
        season, league_id = value.split("=", 1)
        return int(season), league_id.strip()
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("use YEAR=LEAGUE_ID") from exc


def parse_grid(value: str) -> list[float]:
    try:
        values = sorted({float(item) for item in value.split(",")})
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "grid must be comma-separated numbers"
        ) from exc
    if not values or any(value < 0 for value in values):
        raise argparse.ArgumentTypeError("grid values must be non-negative")
    return values


def load_players(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("players file must contain a JSON object")
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def roster_model(
    user: str, roster_id: int, player_ids: list[str], league_id: str
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
        user_id=user,
        league_id=league_id,
    )


def load_league_run(
    season: int,
    league_id: str,
    players: dict[str, dict[str, Any]],
    cache: JsonCache,
) -> LeagueRun:
    raw_league = cache.get(
        f"sleeper_league_{league_id}", f"{SLEEPER_API}/league/{league_id}"
    )
    league = LeagueModel.from_api(raw_league)
    draft_id = str(raw_league.get("draft_id") or league.draft_id)
    raw_draft = cache.get(
        f"sleeper_draft_{draft_id}", f"{SLEEPER_API}/draft/{draft_id}"
    )
    raw_picks = cache.get(
        f"sleeper_draft_picks_{draft_id}", f"{SLEEPER_API}/draft/{draft_id}/picks"
    )
    picks = sorted(
        (DraftPickModel.from_api(item) for item in raw_picks),
        key=lambda pick: pick.pick_number,
    )
    draft_type = str(raw_draft.get("type") or "snake").lower()

    espn_path = cache.root / f"espn_projections_{season}.json"
    if cache.refresh:
        espn_path.unlink(missing_ok=True)
    projection_data = EspnClient(timeout=60).get_nfl_projections(
        str(season), espn_path, max_age=timedelta(days=36500)
    )
    projections = map_projections_to_sleeper(
        projection_data, players, str(season), week=None
    )
    return LeagueRun(
        season=season,
        league_id=league_id,
        draft_type=draft_type,
        league=league,
        picks=picks,
        raw_picks=raw_picks,
        projections=projections,
    )


def weekly_stats(cache: JsonCache, season: int, week: int) -> dict[str, dict[str, Any]]:
    data = cache.get(
        f"sleeper_stats_{season}_{week}",
        f"https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular",
    )
    return data if isinstance(data, dict) else {}


def build_observations(
    run: LeagueRun,
    players: dict[str, dict[str, Any]],
    cache: JsonCache,
) -> list[Observation]:
    pick_by_number = {pick.pick_number: pick for pick in run.picks}
    roster_by_pick: dict[int, int] = {}
    drafted: dict[int, list[str]] = {}
    user_by_roster: dict[int, str] = {}
    for raw in run.raw_picks:
        pick_no = int(raw.get("pick_no") or 0)
        roster_id = int(raw.get("roster_id") or 0)
        pick = pick_by_number.get(pick_no)
        if pick is None:
            continue
        roster_by_pick[pick_no] = roster_id
        drafted.setdefault(roster_id, []).append(pick.player_id)
        user_by_roster.setdefault(roster_id, pick.picked_by)

    deployed = {pick.pick_number: 0.0 for pick in run.picks}
    optimal = {pick.pick_number: 0.0 for pick in run.picks}
    playoff_week = int(run.league.settings.playoff_start_week)
    for week in range(1, playoff_week):
        matchups = cache.get(
            f"sleeper_matchups_{run.league_id}_{week}",
            f"{SLEEPER_API}/league/{run.league_id}/matchups/{week}",
        )
        for matchup in matchups:
            roster_id = int(matchup.get("roster_id") or 0)
            starters = {str(value) for value in matchup.get("starters") or []}
            points = matchup.get("players_points") or {}
            for pick in run.picks:
                if (
                    roster_by_pick.get(pick.pick_number) == roster_id
                    and pick.player_id in starters
                ):
                    deployed[pick.pick_number] += float(points.get(pick.player_id) or 0)

        stats = weekly_stats(cache, run.season, week)
        for roster_id, player_ids in drafted.items():
            user = user_by_roster[roster_id]
            full = roster_model(user, roster_id, player_ids, run.league_id)
            base = optimize_lineup(full, run.league, players, stats).score
            for pick in run.picks:
                if roster_by_pick.get(pick.pick_number) != roster_id:
                    continue
                reduced_ids = [value for value in player_ids if value != pick.player_id]
                reduced = roster_model(user, roster_id, reduced_ids, run.league_id)
                without = optimize_lineup(reduced, run.league, players, stats).score
                optimal[pick.pick_number] += max(0.0, base - without)

    observations = []
    for pick in run.picks:
        roster_id = roster_by_pick.get(pick.pick_number, 0)
        position = str(players.get(pick.player_id, {}).get("position") or "")
        if position not in POSITIONS:
            continue
        observations.append(
            Observation(
                season=run.season,
                league_id=run.league_id,
                pick=pick.pick_number,
                user=pick.picked_by,
                roster_id=roster_id,
                position=position,
                draft_type=run.draft_type,
                deployed=deployed[pick.pick_number],
                optimal=optimal[pick.pick_number],
            )
        )
    return observations


def component_scores(
    run: LeagueRun,
    players: dict[str, dict[str, Any]],
    bench_depth: float,
    tier_drop: float,
) -> dict[int, tuple[float, float, float]]:
    grades = grade_draft_picks(
        run.league,
        run.picks,
        players,
        run.projections,
        DraftGradeWeights(
            strength=1.0,
            roster_fit=1.0,
            cost=1.0,
            bench_depth=bench_depth,
            wait_cost=tier_drop,
        ),
    )
    return {
        number: (
            grade.strength_score,
            grade.roster_fit_score,
            grade.cost_score or 0.0,
        )
        for number, grade in grades.items()
    }


def standardize_by_group(values: np.ndarray, groups: np.ndarray) -> np.ndarray:
    result = np.zeros_like(values, dtype=float)
    for group in np.unique(groups):
        mask = groups == group
        spread = float(values[mask].std())
        if spread > 1e-12:
            result[mask] = (values[mask] - values[mask].mean()) / spread
    return result


def controls_matrix(observations: list[Observation]) -> np.ndarray:
    n = len(observations)
    seasons = sorted({item.season for item in observations})
    positions = sorted({item.position for item in observations})
    progress = np.array(
        [
            (item.pick - 1)
            / max(
                1,
                sum(other.season == item.season for other in observations) - 1,
            )
            for item in observations
        ]
    )
    columns = [np.ones(n), progress, progress**2]
    columns.extend(
        np.array([item.season == season for item in observations], dtype=float)
        for season in seasons[1:]
    )
    columns.extend(
        np.array([item.position == position for item in observations], dtype=float)
        for position in positions[1:]
    )
    return np.column_stack(columns)


def residualize(values: np.ndarray, controls: np.ndarray) -> np.ndarray:
    return values - controls @ np.linalg.lstsq(controls, values, rcond=None)[0]


def nonnegative_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    best_beta = np.zeros(x.shape[1])
    best_loss = float("inf")
    for size in range(1, x.shape[1] + 1):
        for subset in itertools.combinations(range(x.shape[1]), size):
            beta = np.zeros(x.shape[1])
            fitted = np.linalg.lstsq(x[:, subset], y, rcond=None)[0]
            if np.any(fitted < 0):
                continue
            beta[list(subset)] = fitted
            loss = float(np.mean((y - x @ beta) ** 2))
            if loss < best_loss:
                best_loss, best_beta = loss, beta
    return best_beta


def model_arrays(
    observations: list[Observation],
    scores: dict[tuple[int, int], tuple[float, float, float]],
    target: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    seasons = np.array([item.season for item in observations])
    raw_y = np.array([getattr(item, target) for item in observations], dtype=float)
    y = standardize_by_group(np.log1p(np.maximum(0, raw_y)), seasons)
    raw_x = np.array([scores[(item.season, item.pick)] for item in observations])
    x = np.column_stack(
        [
            standardize_by_group(raw_x[:, 0], seasons),
            standardize_by_group(raw_x[:, 1], seasons),
            standardize_by_group(
                raw_x[:, 2],
                np.array(
                    [
                        f"{item.season}-{item.draft_type}"
                        if item.draft_type == "auction"
                        else "snake"
                        for item in observations
                    ]
                ),
            ),
        ]
    )
    x[np.array([item.draft_type != "auction" for item in observations]), 2] = 0
    return x, y, controls_matrix(observations)


def cross_validated_mse(
    observations: list[Observation],
    scores: dict[tuple[int, int], tuple[float, float, float]],
    target: str,
) -> float:
    x, y, controls = model_arrays(observations, scores, target)
    clusters = np.array([f"{item.season}-{item.user}" for item in observations])
    errors = []
    for cluster in np.unique(clusters):
        train = clusters != cluster
        test = ~train
        train_x = residualize(x[train], controls[train])
        train_y = residualize(y[train], controls[train])
        beta = nonnegative_fit(train_x, train_y)
        control_beta = np.linalg.lstsq(
            controls[train], y[train] - x[train] @ beta, rcond=None
        )[0]
        errors.extend((y[test] - controls[test] @ control_beta - x[test] @ beta) ** 2)
    return float(np.mean(errors))


def normalized_weights(beta: np.ndarray) -> list[float]:
    total = float(beta.sum())
    if total <= 0:
        return [0.0] * len(beta)
    return [float(value / total) for value in beta]


def bootstrap_weights(
    observations: list[Observation],
    scores: dict[tuple[int, int], tuple[float, float, float]],
    target: str,
    draws: int,
    seed: int,
) -> list[list[float]]:
    x, y, controls = model_arrays(observations, scores, target)
    clusters = np.array([f"{item.season}-{item.user}" for item in observations])
    unique = np.unique(clusters)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(draws):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        indices = np.concatenate(
            [np.flatnonzero(clusters == value) for value in sampled]
        )
        rx = residualize(x[indices], controls[indices])
        ry = residualize(y[indices], controls[indices])
        estimates.append(normalized_weights(nonnegative_fit(rx, ry)))
    return estimates


def percentile_intervals(estimates: list[list[float]]) -> list[list[float]]:
    if not estimates:
        return []
    values = np.asarray(estimates)
    return [
        [
            float(np.quantile(values[:, index], 0.025)),
            float(np.quantile(values[:, index], 0.975)),
        ]
        for index in range(values.shape[1])
    ]


def round_step(value: float, step: float = 0.05) -> float:
    return math.floor(value / step + 0.5) * step


def spearman(left: list[float], right: list[float]) -> float:
    if len(left) < 2:
        return float("nan")

    def ranks(values: list[float]) -> np.ndarray:
        order = np.argsort(values)
        result = np.empty(len(values), dtype=float)
        start = 0
        while start < len(values):
            end = start + 1
            while end < len(values) and values[order[end]] == values[order[start]]:
                end += 1
            result[order[start:end]] = (start + end - 1) / 2
            start = end
        return result

    a, b = ranks(left), ranks(right)
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--league",
        action="append",
        required=True,
        type=parse_league,
        metavar="YEAR=LEAGUE_ID",
    )
    parser.add_argument(
        "--players", type=Path, default=REPO_ROOT / "data/nfl_players.json"
    )
    parser.add_argument(
        "--bench-grid", type=parse_grid, default=parse_grid("0,0.05,0.1,0.15,0.2")
    )
    parser.add_argument(
        "--tier-grid", type=parse_grid, default=parse_grid("0,0.05,0.1,0.15,0.2")
    )
    parser.add_argument("--bootstrap-draws", type=int, default=1000)
    parser.add_argument("--auction-cost-prior", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/fantasy-dashboard-calibration"),
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if len(args.league) < 2:
        raise SystemExit("provide at least two --league YEAR=LEAGUE_ID values")
    players = load_players(args.players)
    cache = JsonCache(args.cache_dir, args.refresh)
    runs = [
        load_league_run(season, league_id, players, cache)
        for season, league_id in args.league
    ]
    observations = [
        item for run in runs for item in build_observations(run, players, cache)
    ]

    score_cache: dict[
        tuple[int, float, float], dict[int, tuple[float, float, float]]
    ] = {}

    def scores_for(
        bench: float, tier: float
    ) -> dict[tuple[int, int], tuple[float, float, float]]:
        combined = {}
        for run in runs:
            key = (run.season, bench, tier)
            if key not in score_cache:
                score_cache[key] = component_scores(run, players, bench, tier)
            combined.update(
                {
                    (run.season, pick): values
                    for pick, values in score_cache[key].items()
                }
            )
        return combined

    target_results = {}
    selected_pairs = []
    conditional_strength = []
    for target in ("deployed", "optimal"):
        candidates = []
        for bench in args.bench_grid:
            for tier in args.tier_grid:
                scores = scores_for(bench, tier)
                candidates.append(
                    {
                        "bench_depth": bench,
                        "tier_drop": tier,
                        "cv_mse": cross_validated_mse(observations, scores, target),
                    }
                )
        selected = min(candidates, key=lambda item: item["cv_mse"])
        selected_pairs.append((selected["bench_depth"], selected["tier_drop"]))
        scores = scores_for(selected["bench_depth"], selected["tier_drop"])
        x, y, controls = model_arrays(observations, scores, target)
        beta = nonnegative_fit(residualize(x, controls), residualize(y, controls))
        weights = normalized_weights(beta)
        strength_fit = weights[0] + weights[1]
        conditional_strength.append(weights[0] / strength_fit if strength_fit else 0.5)
        intervals = percentile_intervals(
            bootstrap_weights(
                observations, scores, target, args.bootstrap_draws, args.seed
            )
        )
        target_results[target] = {
            "selected": selected,
            "normalized_primary_weights": dict(
                zip(("strength", "fit", "cost"), weights, strict=True)
            ),
            "bootstrap_95pct_intervals": dict(
                zip(("strength", "fit", "cost"), intervals, strict=True)
            ),
            "grid_validation": sorted(candidates, key=lambda item: item["cv_mse"]),
        }

    strength_share = round_step(float(np.mean(conditional_strength)))
    bench = round_step(float(np.mean([value[0] for value in selected_pairs])))
    tier = round_step(float(np.mean([value[1] for value in selected_pairs])))
    cost = args.auction_cost_prior
    remaining = 1.0 - cost
    recommendations = {
        "snake": {
            "strength": strength_share,
            "fit": 1.0 - strength_share,
            "cost": 0.0,
        },
        "auction": {
            "strength": remaining * strength_share,
            "fit": remaining * (1.0 - strength_share),
            "cost": cost,
        },
        "bench_depth": bench,
        "tier_drop": tier,
    }

    recommended_scores = scores_for(bench, tier)
    validation = {}
    for target in ("deployed", "optimal"):
        validation[target] = {}
        for season in sorted({item.season for item in observations}):
            subset = [item for item in observations if item.season == season]
            predicted = []
            actual = []
            for item in subset:
                strength, fit, cost_score = recommended_scores[(season, item.pick)]
                weights = (
                    recommendations["auction"]
                    if item.draft_type == "auction"
                    else recommendations["snake"]
                )
                predicted.append(
                    weights["strength"] * strength
                    + weights["fit"] * fit
                    + weights["cost"] * cost_score
                )
                actual.append(getattr(item, target))
            validation[target][str(season)] = {
                "spearman": spearman(predicted, actual),
                "n": len(subset),
            }

    seasons = sorted({run.season for run in runs})
    output = args.output or (
        REPO_ROOT
        / "analysis/results"
        / f"draft_weights_{min(seasons)}_{max(seasons)}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "method": {
            "targets": [
                "actual regular-season starter points for original team",
                "marginal points in optimal draft-only weekly lineup",
            ],
            "validation": "leave-one-team-season-out",
            "response": "within-season standardized log1p points",
            "controls": [
                "season",
                "pick progress",
                "pick progress squared",
                "position",
            ],
            "constraints": "non-negative strength/fit/cost coefficients",
            "stabilization": (
                "average target-specific strength share; round to 0.05; "
                "apply auction cost prior because one auction season weakly identifies cost"
            ),
        },
        "inputs": {
            "leagues": [
                {
                    "season": run.season,
                    "league_id": run.league_id,
                    "draft_type": run.draft_type,
                    "picks": len(run.picks),
                }
                for run in runs
            ],
            "half_ppr_verified": all(
                float(run.league.scoring_settings.get("rec") or 0) == 0.5
                for run in runs
            ),
            "observations": len(observations),
            "bench_grid": args.bench_grid,
            "tier_grid": args.tier_grid,
        },
        "target_models": target_results,
        "recommended_defaults": recommendations,
        "validation": validation,
        "caveats": [
            "ESPN historical season projections may not be a timestamped draft-day snapshot.",
            "Auction cost is weakly identified when the input includes only one auction season.",
            "Individual pick outcomes do not capture every roster-level auction budget externality.",
            "Treat two-season estimates as shrinkage-calibrated defaults, not universal constants.",
        ],
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(recommendations, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
