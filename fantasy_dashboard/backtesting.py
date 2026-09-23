import json
import sqlite3
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any

from fantasy_dashboard.paths import SNAPSHOT_DATABASE_PATH


@dataclass(frozen=True, slots=True)
class SnapshotWeek:
    season: int
    week: int
    projection_run_id: str
    actual_run_id: str
    projected_at: str
    actual_captured_at: str
    projections: dict[str, dict[str, Any]]
    actuals: dict[str, dict[str, Any]]


def _stats_for_run(
    connection: sqlite3.Connection,
    run_id: str,
    stat_type: str,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT player_id, stats_json
        FROM player_stat_snapshots
        WHERE run_id = ? AND stat_type = ?
        """,
        (run_id, stat_type),
    )
    stats: dict[str, dict[str, Any]] = {}
    for player_id, stats_json in rows:
        try:
            value = json.loads(stats_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            stats[str(player_id)] = value
    return stats


def load_completed_snapshot_weeks(
    league_id: str,
    season: str | int,
    database_path: Path = SNAPSHOT_DATABASE_PATH,
) -> dict[int, SnapshotWeek]:
    """Load the latest paired pre-kickoff and post-week run for each week."""
    path = Path(database_path)
    if not path.is_file():
        return {}

    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            run_rows = connection.execute(
                """
                SELECT run_id, snapshot_type, week, captured_at
                FROM snapshot_runs
                WHERE league_id = ? AND season = ?
                  AND snapshot_type IN ('pre-kickoff', 'post-week')
                ORDER BY week, snapshot_type, captured_at DESC
                """,
                (str(league_id), str(season)),
            ).fetchall()
            latest: dict[tuple[int, str], tuple[str, str]] = {}
            for run_id, snapshot_type, week, captured_at in run_rows:
                latest.setdefault(
                    (int(week), str(snapshot_type)),
                    (str(run_id), str(captured_at)),
                )

            completed: dict[int, SnapshotWeek] = {}
            weeks = sorted({week for week, _ in latest})
            for week in weeks:
                pre_run = latest.get((week, "pre-kickoff"))
                post_run = latest.get((week, "post-week"))
                if pre_run is None or post_run is None:
                    continue
                projections = _stats_for_run(connection, pre_run[0], "projection")
                actuals = _stats_for_run(connection, post_run[0], "actual")
                if not projections or not actuals:
                    continue
                completed[week] = SnapshotWeek(
                    season=int(season),
                    week=week,
                    projection_run_id=pre_run[0],
                    actual_run_id=post_run[0],
                    projected_at=pre_run[1],
                    actual_captured_at=post_run[1],
                    projections=projections,
                    actuals=actuals,
                )
            return completed
    except sqlite3.DatabaseError:
        return {}


def aggregate_weekly_stats(
    weeks: dict[int, SnapshotWeek],
    stat_type: str,
    selected_week: int | None = None,
) -> dict[str, dict[str, float]]:
    """Sum numeric player statistics across completed snapshot weeks."""
    if stat_type not in {"actual", "projection"}:
        raise ValueError("stat_type must be actual or projection")
    selected_weeks = (
        [selected_week]
        if selected_week is not None and selected_week in weeks
        else sorted(weeks)
        if selected_week is None
        else []
    )
    totals: dict[str, dict[str, float]] = {}
    for week in selected_weeks:
        source = (
            weeks[week].actuals if stat_type == "actual" else weeks[week].projections
        )
        for player_id, stats in source.items():
            player_totals = totals.setdefault(player_id, {})
            for name, value in stats.items():
                if isinstance(value, Real):
                    player_totals[name] = player_totals.get(name, 0.0) + float(value)
    return totals
