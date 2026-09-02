#!/usr/bin/env python3
"""Calibrate weekly fantasy-point coefficients of variation by position."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from fantasy_dashboard.league_predictions import (  # noqa: E402
    DEFAULT_WEEKLY_CV,
    POSITION_WEEKLY_CV,
)
from fantasy_dashboard.player_stats import calculate_fantasy_points  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
DEFAULT_POOL = {
    "QB": 32,
    "RB": 72,
    "WR": 96,
    "TE": 40,
    "K": 32,
    "DEF": 32,
}
SLEEPER_API = "https://api.sleeper.app/v1"


@dataclass(frozen=True)
class PlayerSeason:
    player_id: str
    position: str
    season: int
    points: np.ndarray

    @property
    def mean(self) -> float:
        return float(np.mean(self.points))

    @property
    def standard_deviation(self) -> float:
        return float(np.std(self.points, ddof=0))


class JsonCache:
    def __init__(self, root: Path, refresh: bool) -> None:
        self.root = root
        self.refresh = refresh

    def get(self, name: str, url: str) -> Any:
        path = self.root / name
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload


def parse_position_map(raw: str) -> dict[str, int]:
    values = dict(DEFAULT_POOL)
    for item in raw.split(","):
        position, count = item.split("=", 1)
        position = position.strip().upper()
        if position not in POSITIONS:
            raise argparse.ArgumentTypeError(f"Unsupported position: {position}")
        values[position] = int(count)
    return values


def load_scoring_settings(
    database: Path,
    scoring_league_id: str | None,
    cache: JsonCache,
) -> tuple[dict[str, float], str]:
    if scoring_league_id:
        league = cache.get(
            f"sleeper/league_{scoring_league_id}.json",
            f"{SLEEPER_API}/league/{scoring_league_id}",
        )
        return (
            {
                key: float(value)
                for key, value in (league.get("scoring_settings") or {}).items()
            },
            f"Sleeper league {scoring_league_id}",
        )

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT l.league_id, l.scoring_settings_json
            FROM league_snapshots AS l
            JOIN snapshot_runs AS r USING (run_id)
            ORDER BY r.captured_at DESC
            """
        )
        for league_id, raw_settings in rows:
            settings = json.loads(raw_settings)
            if float(settings.get("rec", 0)) == 0.5:
                return (
                    {key: float(value) for key, value in settings.items()},
                    f"latest saved half-PPR league {league_id}",
                )
    raise RuntimeError(
        "No half-PPR scoring settings found. Pass --scoring-league-id."
    )


def participated(position: str, stats: dict[str, Any]) -> bool:
    if not stats.get("gp") and not stats.get("gms_active"):
        return False
    if position == "QB":
        return bool(stats.get("pass_att") or stats.get("rush_att"))
    if position in {"RB", "WR", "TE"}:
        return bool(
            stats.get("rush_att") or stats.get("rec_tgt") or stats.get("rec")
        )
    if position == "K":
        return bool(stats.get("fga") or stats.get("xpa"))
    return position == "DEF"


def load_player_seasons(
    seasons: list[int],
    players_path: Path,
    settings: dict[str, float],
    min_games: int,
    cache: JsonCache,
) -> tuple[list[PlayerSeason], int]:
    players = json.loads(players_path.read_text(encoding="utf-8"))
    weekly: dict[tuple[str, str, int], list[float]] = {}
    unmapped = 0
    for season in seasons:
        for week in range(1, 19):
            payload = cache.get(
                f"sleeper/stats_regular_{season}_{week}.json",
                f"{SLEEPER_API}/stats/nfl/regular/{season}/{week}",
            )
            for player_id, stats in payload.items():
                position = str(players.get(player_id, {}).get("position") or "")
                if not position:
                    unmapped += 1
                if position not in POSITIONS or not participated(position, stats):
                    continue
                points = calculate_fantasy_points(stats, settings)
                weekly.setdefault((player_id, position, season), []).append(points)

    rows = []
    for (player_id, position, season), values in weekly.items():
        points = np.asarray(values, dtype=float)
        if len(points) >= min_games and float(np.mean(points)) > 0:
            rows.append(PlayerSeason(player_id, position, season, points))
    return rows, unmapped


def select_starter_pool(
    rows: list[PlayerSeason],
    seasons: list[int],
    pool_sizes: dict[str, int],
) -> list[PlayerSeason]:
    selected = []
    for season in seasons:
        for position in POSITIONS:
            candidates = [
                row
                for row in rows
                if row.season == season and row.position == position
            ]
            candidates.sort(
                key=lambda row: (row.mean, float(np.sum(row.points))),
                reverse=True,
            )
            selected.extend(candidates[: pool_sizes[position]])
    return selected


def variance_coefficient(rows: list[PlayerSeason]) -> float:
    numerator = sum(
        float(np.sum((row.points - row.mean) ** 2)) for row in rows
    )
    denominator = sum(len(row.points) * row.mean**2 for row in rows)
    return math.sqrt(numerator / denominator)


def standard_deviation_ols(rows: list[PlayerSeason]) -> float:
    numerator = sum(
        row.mean * row.standard_deviation for row in rows
    )
    denominator = sum(row.mean**2 for row in rows)
    return numerator / denominator


def log_standard_deviation_regression(
    rows: list[PlayerSeason],
    seasons: list[int],
) -> dict[str, Any]:
    usable = [
        row
        for row in rows
        if row.mean > 0 and row.standard_deviation > 0
    ]
    baseline = seasons[0]
    columns = [
        np.ones(len(usable)),
        np.log([row.mean for row in usable]),
    ]
    for season in seasons[1:]:
        columns.append(
            np.asarray(
                [1.0 if row.season == season else 0.0 for row in usable]
            )
        )
    features = np.column_stack(columns)
    target = np.log([row.standard_deviation for row in usable])
    coefficients, *_ = np.linalg.lstsq(features, target, rcond=None)
    fitted = features @ coefficients
    denominator = float(np.sum((target - np.mean(target)) ** 2))
    r_squared = (
        1 - float(np.sum((target - fitted) ** 2)) / denominator
        if denominator
        else 0.0
    )
    return {
        "baseline_season": baseline,
        "intercept": float(coefficients[0]),
        "mean_elasticity": float(coefficients[1]),
        "season_effects": {
            str(season): float(coefficients[index + 2])
            for index, season in enumerate(seasons[1:])
        },
        "r_squared": r_squared,
    }


def bootstrap_interval(
    rows: list[PlayerSeason],
    draws: int,
    seed: int,
) -> list[float] | None:
    if draws <= 0:
        return None
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(draws):
        sample = [
            rows[index]
            for index in rng.integers(0, len(rows), len(rows))
        ]
        estimates.append(variance_coefficient(sample))
    return [
        float(value)
        for value in np.quantile(estimates, [0.025, 0.975])
    ]


def normal_log_score(rows: list[PlayerSeason], coefficient: float) -> float:
    terms: list[float] = []
    for row in rows:
        deviation = max(1.0, coefficient * row.mean)
        residual = row.points - row.mean
        terms.extend(
            np.log(deviation) + 0.5 * (residual / deviation) ** 2
        )
    return float(np.mean(terms))


def one_standard_deviation_coverage(
    rows: list[PlayerSeason],
    coefficient: float,
) -> float:
    covered = 0
    total = 0
    for row in rows:
        deviation = max(1.0, coefficient * row.mean)
        covered += int(
            np.sum(np.abs(row.points - row.mean) <= deviation)
        )
        total += len(row.points)
    return covered / total


def current_coefficient(position: str) -> float:
    return float(POSITION_WEEKLY_CV.get(position, DEFAULT_WEEKLY_CV))


def calibrate(
    rows: list[PlayerSeason],
    seasons: list[int],
    bootstrap_draws: int,
    seed: int,
) -> dict[str, Any]:
    results = {}
    for index, position in enumerate(POSITIONS):
        position_rows = [row for row in rows if row.position == position]
        if not position_rows:
            results[position] = {"error": "No eligible observations"}
            continue
        fitted = variance_coefficient(position_rows)
        current = current_coefficient(position)
        by_season = {}
        for season in seasons:
            season_rows = [
                row for row in position_rows if row.season == season
            ]
            by_season[str(season)] = (
                variance_coefficient(season_rows) if season_rows else None
            )

        holdout = None
        if len(seasons) >= 2:
            latest = seasons[-1]
            training = [
                row for row in position_rows if row.season < latest
            ]
            testing = [
                row for row in position_rows if row.season == latest
            ]
            if training and testing:
                training_fit = variance_coefficient(training)
                current_score = normal_log_score(testing, current)
                fitted_score = normal_log_score(testing, training_fit)
                holdout = {
                    "training_seasons": seasons[:-1],
                    "testing_season": latest,
                    "training_coefficient": training_fit,
                    "current_log_score": current_score,
                    "fitted_log_score": fitted_score,
                    "relative_improvement": (
                        (current_score - fitted_score) / current_score
                        if current_score
                        else 0.0
                    ),
                }

        results[position] = {
            "player_seasons": len(position_rows),
            "player_weeks": sum(len(row.points) for row in position_rows),
            "current_coefficient": current,
            "coefficient_variance_fit": fitted,
            "coefficient_sd_ols": standard_deviation_ols(position_rows),
            "bootstrap_95": bootstrap_interval(
                position_rows,
                bootstrap_draws,
                seed + index,
            ),
            "by_season": by_season,
            "log_sd_regression": log_standard_deviation_regression(
                position_rows,
                seasons,
            ),
            "one_sd_coverage": {
                "current": one_standard_deviation_coverage(
                    position_rows,
                    current,
                ),
                "fitted": one_standard_deviation_coverage(
                    position_rows,
                    fitted,
                ),
            },
            "forward_holdout": holdout,
        }
    return results


def default_output(seasons: list[int]) -> Path:
    suffix = "_".join(str(season) for season in seasons)
    return Path("analysis/results") / f"positional_cv_{suffix}.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    parser.add_argument(
        "--scoring-league-id",
        help="Load scoring settings directly from this Sleeper league.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/fantasy_dashboard.sqlite3"),
    )
    parser.add_argument(
        "--players",
        type=Path,
        default=Path("data/nfl_players.json"),
    )
    parser.add_argument("--min-games", type=int, default=8)
    parser.add_argument(
        "--starter-pool",
        type=parse_position_map,
        default=dict(DEFAULT_POOL),
        metavar="QB=32,RB=72,WR=96,TE=40,K=32,DEF=32",
    )
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/tmp/fantasy-dashboard-calibration"),
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    seasons = sorted(set(args.seasons))
    cache = JsonCache(args.cache_dir, args.refresh)
    settings, scoring_source = load_scoring_settings(
        args.database,
        args.scoring_league_id,
        cache,
    )
    rows, unmapped = load_player_seasons(
        seasons,
        args.players,
        settings,
        args.min_games,
        cache,
    )
    starter_rows = select_starter_pool(
        rows,
        seasons,
        args.starter_pool,
    )
    output = {
        "method": {
            "seasons": seasons,
            "weeks": [1, 18],
            "scoring_source": scoring_source,
            "minimum_participating_games": args.min_games,
            "starter_pool_size_per_season": args.starter_pool,
            "participation": (
                "position-specific recorded opportunity; DEF requires a "
                "played game"
            ),
            "bootstrap_draws": args.bootstrap_draws,
            "seed": args.seed,
            "unmapped_player_week_rows": unmapped,
        },
        "starter_pool": calibrate(
            starter_rows,
            seasons,
            args.bootstrap_draws,
            args.seed,
        ),
        "broad_pool": calibrate(
            rows,
            seasons,
            args.bootstrap_draws,
            args.seed + 100,
        ),
    }
    output_path = args.output or default_output(seasons)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
