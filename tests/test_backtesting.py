import json
import sqlite3
from pathlib import Path

from fantasy_dashboard.backtesting import (
    aggregate_weekly_stats,
    load_completed_snapshot_weeks,
)


def _snapshot_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE snapshot_runs (
                run_id TEXT PRIMARY KEY,
                snapshot_type TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                league_id TEXT NOT NULL,
                season TEXT NOT NULL,
                season_type TEXT NOT NULL,
                week INTEGER NOT NULL,
                archive_path TEXT NOT NULL,
                player_catalog_sha256 TEXT NOT NULL
            );
            CREATE TABLE player_stat_snapshots (
                run_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                stat_type TEXT NOT NULL,
                provider TEXT NOT NULL,
                nfl_team TEXT,
                game_key TEXT,
                fantasy_points REAL NOT NULL,
                stats_json TEXT NOT NULL,
                PRIMARY KEY (run_id, player_id, stat_type, provider)
            );
            """
        )
        runs = [
            ("pre-old", "pre-kickoff", "2026-09-01T00:00:00Z", 1),
            ("pre-new", "pre-kickoff", "2026-09-02T00:00:00Z", 1),
            ("post-1", "post-week", "2026-09-09T00:00:00Z", 1),
            ("pre-2", "pre-kickoff", "2026-09-10T00:00:00Z", 2),
        ]
        connection.executemany(
            "INSERT INTO snapshot_runs VALUES (?, ?, ?, 'league-1', '2026', "
            "'regular', ?, '', '')",
            runs,
        )
        stats = [
            ("pre-old", "p1", "projection", "espn", 8, {"pts": 8}),
            ("pre-new", "p1", "projection", "espn", 10, {"pts": 10}),
            ("post-1", "p1", "actual", "sleeper", 12, {"gp": 1, "pts": 12}),
            ("pre-2", "p1", "projection", "espn", 11, {"pts": 11}),
        ]
        connection.executemany(
            "INSERT INTO player_stat_snapshots VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
            [(*row[:5], json.dumps(row[5])) for row in stats],
        )


def test_loads_latest_complete_projection_actual_pair(tmp_path: Path) -> None:
    database_path = tmp_path / "snapshots.sqlite3"
    _snapshot_database(database_path)

    weeks = load_completed_snapshot_weeks("league-1", 2026, database_path)

    assert list(weeks) == [1]
    assert weeks[1].projection_run_id == "pre-new"
    assert weeks[1].projections["p1"] == {"pts": 10}
    assert weeks[1].actuals["p1"] == {"gp": 1, "pts": 12}
    assert aggregate_weekly_stats(weeks, "projection") == {"p1": {"pts": 10}}
    assert aggregate_weekly_stats(weeks, "actual", 1) == {"p1": {"gp": 1, "pts": 12}}


def test_missing_or_invalid_snapshot_database_is_empty(tmp_path: Path) -> None:
    assert load_completed_snapshot_weeks("league-1", 2026, tmp_path / "missing") == {}
    invalid_path = tmp_path / "invalid.sqlite3"
    invalid_path.write_text("not sqlite", encoding="utf-8")
    assert load_completed_snapshot_weeks("league-1", 2026, invalid_path) == {}
