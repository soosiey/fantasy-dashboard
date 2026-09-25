import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from fantasy_dashboard.backtesting import load_completed_snapshot_weeks
from fantasy_dashboard.paths import DATA_DIR
from fantasy_dashboard.regression_cache import load_or_create_regression_artifact


def _load_context(
    database_path: Path,
    league_id: str,
) -> tuple[int, dict[str, Any]]:
    with sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro", uri=True
    ) as connection:
        row = connection.execute(
            """
            SELECT sr.season, ls.scoring_settings_json
            FROM snapshot_runs AS sr
            JOIN league_snapshots AS ls USING (run_id)
            WHERE sr.league_id = ?
            ORDER BY sr.captured_at DESC
            LIMIT 1
            """,
            (str(league_id),),
        ).fetchone()
    if row is None:
        raise ValueError(f"No snapshots exist for league {league_id}.")
    scoring_settings = json.loads(row[1])
    if not isinstance(scoring_settings, dict):
        raise TypeError("Snapshot scoring settings must be an object.")
    return int(row[0]), scoring_settings


def _load_players(players_path: Path) -> dict[str, dict[str, Any]]:
    with players_path.open(encoding="utf-8") as players_file:
        payload = json.load(players_file)
    if not isinstance(payload, dict):
        raise TypeError("The player catalog must be an object.")
    return {
        str(player_id): player
        for player_id, player in payload.items()
        if isinstance(player, dict)
    }


def warm_league_cache(storage_dir: Path, league_id: str) -> bool:
    database_path = storage_dir / "fantasy_dashboard.sqlite3"
    season, scoring_settings = _load_context(database_path, league_id)
    snapshots = load_completed_snapshot_weeks(
        league_id,
        season,
        database_path,
    )
    if not snapshots:
        print(
            f"Skipped regression cache for league {league_id}, season {season}; "
            "no completed projection/actual snapshot pairs yet."
        )
        return False
    artifact = load_or_create_regression_artifact(
        league_id,
        season,
        _load_players(storage_dir / "nfl_players.json"),
        scoring_settings,
        snapshots,
        cache_dir=storage_dir / "cache" / "regression",
    )
    if artifact is None:
        raise ValueError(f"Regression cache was not created for league {league_id}.")
    action = "Loaded" if artifact.loaded_from_cache else "Rebuilt"
    weeks = ", ".join(str(week) for week in artifact.completed_weeks)
    print(
        f"{action} regression cache for league {league_id}, season {season}; "
        f"completed weeks: {weeks}; player-weeks: "
        f"{len(artifact.backtest_predictions)}."
    )
    return not artifact.loaded_from_cache


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build persistent regression caches from completed snapshots."
    )
    parser.add_argument("--league-id", action="append", required=True)
    parser.add_argument(
        "--storage-dir",
        type=Path,
        default=DATA_DIR,
        help=f"Snapshot and cache directory (default: {DATA_DIR}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    failed = False
    for league_id in arguments.league_id:
        try:
            warm_league_cache(arguments.storage_dir, str(league_id))
        except (
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            sqlite3.Error,
        ) as error:
            failed = True
            print(
                f"Regression cache warm-up failed for league {league_id}: {error}",
                file=sys.stderr,
            )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
