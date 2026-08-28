import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests

from fantasy_dashboard.clients.espn import (
    EspnClient,
    map_projections_to_sleeper,
)
from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.paths import NFL_PLAYERS_PATH, SNAPSHOT_STORAGE_DIR
from fantasy_dashboard.player_stats import calculate_fantasy_points

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshot_runs (
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

CREATE TABLE IF NOT EXISTS league_snapshots (
    run_id TEXT PRIMARY KEY REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    league_id TEXT NOT NULL,
    name TEXT,
    status TEXT,
    season TEXT NOT NULL,
    season_type TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    scoring_settings_json TEXT NOT NULL,
    roster_positions_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scoring_setting_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    stat_name TEXT NOT NULL,
    points REAL NOT NULL,
    PRIMARY KEY (run_id, stat_name)
);

CREATE TABLE IF NOT EXISTS league_user_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    display_name TEXT,
    team_name TEXT,
    avatar_id TEXT,
    PRIMARY KEY (run_id, user_id)
);

CREATE TABLE IF NOT EXISTS roster_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    roster_id INTEGER NOT NULL,
    owner_id TEXT,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    ties INTEGER NOT NULL,
    points_for REAL NOT NULL,
    points_against REAL NOT NULL,
    settings_json TEXT NOT NULL,
    PRIMARY KEY (run_id, roster_id)
);

CREATE TABLE IF NOT EXISTS roster_player_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    roster_id INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    roster_status TEXT NOT NULL,
    PRIMARY KEY (run_id, roster_id, player_id)
);

CREATE TABLE IF NOT EXISTS matchup_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    roster_id INTEGER NOT NULL,
    matchup_id INTEGER,
    points REAL NOT NULL,
    custom_points REAL,
    PRIMARY KEY (run_id, roster_id)
);

CREATE TABLE IF NOT EXISTS matchup_player_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    roster_id INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    is_starter INTEGER NOT NULL,
    points REAL NOT NULL,
    PRIMARY KEY (run_id, roster_id, player_id)
);

CREATE TABLE IF NOT EXISTS game_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    game_key TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    kickoff_at TEXT,
    status TEXT,
    game_json TEXT NOT NULL,
    PRIMARY KEY (run_id, game_key)
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    team TEXT,
    espn_id TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_stat_snapshots (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    stat_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    fantasy_points REAL NOT NULL,
    stats_json TEXT NOT NULL,
    PRIMARY KEY (run_id, player_id, stat_type, provider)
);

CREATE TABLE IF NOT EXISTS player_stat_values (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    stat_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    stat_name TEXT NOT NULL,
    stat_value REAL NOT NULL,
    PRIMARY KEY (run_id, player_id, stat_type, provider, stat_name)
);

CREATE TABLE IF NOT EXISTS snapshot_artifacts (
    run_id TEXT NOT NULL REFERENCES snapshot_runs(run_id) ON DELETE CASCADE,
    artifact_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    PRIMARY KEY (run_id, artifact_name)
);
"""


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    run_id: str
    archive_path: Path
    database_path: Path
    player_stat_count: int


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(value, temporary_file, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numeric(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _points_from_settings(settings: dict[str, Any], prefix: str) -> float:
    return _numeric(settings.get(prefix)) + _numeric(
        settings.get(f"{prefix}_decimal")
    ) / 100


def _game_key(game: dict[str, Any], index: int) -> str:
    identifier = game.get("game_id") or game.get("gameId") or game.get("id")
    if identifier is not None:
        return str(identifier)
    return "-".join(
        (
            str(game.get("week") or ""),
            str(game.get("away") or game.get("away_team") or ""),
            str(game.get("home") or game.get("home_team") or ""),
            str(index),
        )
    )


class SnapshotCollector:
    def __init__(
        self,
        storage_dir: Path = SNAPSHOT_STORAGE_DIR,
        players_path: Path = NFL_PLAYERS_PATH,
        sleeper_client: SleeperClient | None = None,
        espn_client: EspnClient | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.players_path = Path(players_path)
        self.sleeper = sleeper_client or SleeperClient(timeout=30.0)
        self.espn = espn_client or EspnClient(timeout=30.0)

    def collect(
        self,
        snapshot_type: str,
        league_id: str,
        week: int,
        season: str | None = None,
        season_type: str | None = None,
    ) -> SnapshotResult:
        if snapshot_type not in {"pre-kickoff", "post-week"}:
            raise ValueError("Snapshot type must be pre-kickoff or post-week.")
        if not 1 <= week <= 18:
            raise ValueError("Week must be between 1 and 18.")

        captured_at = datetime.now(timezone.utc).replace(microsecond=0)
        captured_at_text = captured_at.isoformat().replace("+00:00", "Z")
        run_id = str(uuid.uuid4())

        league_data = self._raw_object(f"league/{league_id}")
        resolved_season = str(season or league_data.get("season") or "")
        resolved_season_type = str(
            season_type or league_data.get("season_type") or "regular"
        )
        if not resolved_season:
            raise ValueError("A season was not supplied by the CLI or league.")

        run_folder = (
            self.storage_dir
            / "snapshots"
            / resolved_season
            / f"week_{week:02d}"
            / str(league_id)
            / snapshot_type.replace("-", "_")
            / f"{captured_at:%Y%m%dT%H%M%SZ}_{run_id[:8]}"
        )
        run_folder.mkdir(parents=True, exist_ok=False)

        # Capture league membership and weekly context in every run so a stat
        # snapshot can always be interpreted independently in the future.
        nfl_state = self.sleeper.get_nfl_state()
        users = self._raw_list(f"league/{league_id}/users")
        rosters = self._raw_list(f"league/{league_id}/rosters")
        matchups = self._raw_list(f"league/{league_id}/matchups/{week}")
        schedule = self.sleeper.get_nfl_schedule(
            resolved_season, resolved_season_type
        )
        scoring_settings = league_data.get("scoring_settings") or {}
        if not isinstance(scoring_settings, dict):
            raise TypeError("League scoring settings must be an object.")

        artifacts: dict[str, Path] = {}
        raw_values = {
            "nfl_state": nfl_state,
            "league": league_data,
            "scoring_settings": scoring_settings,
            "users": users,
            "rosters": rosters,
            "matchups": matchups,
            "schedule": schedule,
        }
        for artifact_name, value in raw_values.items():
            artifact_path = run_folder / f"{artifact_name}.json"
            _write_json(artifact_path, value)
            artifacts[artifact_name] = artifact_path

        players, catalog_hash, catalog_path = self._preserve_player_catalog()
        if snapshot_type == "pre-kickoff":
            projection_path = run_folder / "espn_projections.json"
            projection_data = self.espn.get_nfl_projections(
                resolved_season,
                projection_path,
            )
            stats_by_player = map_projections_to_sleeper(
                projection_data,
                players,
                resolved_season,
                week,
            )
            stat_type = "projection"
            provider = "espn"
            artifacts["espn_projections"] = projection_path
        else:
            stats_by_player = self.sleeper.get_player_stats(
                resolved_season,
                resolved_season_type,
                week,
            )
            actual_stats_path = run_folder / "sleeper_player_stats.json"
            _write_json(actual_stats_path, stats_by_player)
            artifacts["sleeper_player_stats"] = actual_stats_path
            stat_type = "actual"
            provider = "sleeper"

        database_path = self.storage_dir / "fantasy_dashboard.sqlite3"
        self._save_database(
            database_path=database_path,
            run_id=run_id,
            snapshot_type=snapshot_type,
            captured_at=captured_at_text,
            league_id=str(league_id),
            season=resolved_season,
            season_type=resolved_season_type,
            week=week,
            run_folder=run_folder,
            catalog_hash=catalog_hash,
            league_data=league_data,
            scoring_settings=scoring_settings,
            users=users,
            rosters=rosters,
            matchups=matchups,
            schedule=schedule,
            players=players,
            stats_by_player=stats_by_player,
            stat_type=stat_type,
            provider=provider,
            artifacts=artifacts,
        )

        manifest = {
            "run_id": run_id,
            "snapshot_type": snapshot_type,
            "captured_at": captured_at_text,
            "league_id": str(league_id),
            "season": resolved_season,
            "season_type": resolved_season_type,
            "week": week,
            "player_catalog": str(catalog_path.relative_to(self.storage_dir)),
            "player_catalog_sha256": catalog_hash,
            "player_stat_count": len(stats_by_player),
            "artifacts": {
                name: {
                    "file": path.name,
                    "sha256": _sha256(path),
                }
                for name, path in artifacts.items()
            },
        }
        _write_json(run_folder / "manifest.json", manifest)

        return SnapshotResult(
            run_id=run_id,
            archive_path=run_folder,
            database_path=database_path,
            player_stat_count=len(stats_by_player),
        )

    def _raw_object(self, endpoint: str) -> dict[str, Any]:
        data = self.sleeper.get_raw_api_data(endpoint)
        if not isinstance(data, dict):
            raise TypeError(f"Sleeper endpoint {endpoint} must return an object.")
        return data

    def _raw_list(self, endpoint: str) -> list[dict[str, Any]]:
        data = self.sleeper.get_raw_api_data(endpoint)
        if not isinstance(data, list):
            raise TypeError(f"Sleeper endpoint {endpoint} must return a list.")
        return [item for item in data if isinstance(item, dict)]

    def _preserve_player_catalog(
        self,
    ) -> tuple[dict[str, dict[str, Any]], str, Path]:
        self.sleeper.refresh_nfl_players_cache(self.players_path)
        with self.players_path.open(encoding="utf-8") as players_file:
            loaded_players = json.load(players_file)
        if not isinstance(loaded_players, dict):
            raise TypeError("The Sleeper player catalog must be an object.")
        players = {
            str(player_id): player
            for player_id, player in loaded_players.items()
            if isinstance(player, dict)
        }

        catalog_hash = _sha256(self.players_path)
        catalog_folder = self.storage_dir / "player_catalogs"
        catalog_folder.mkdir(parents=True, exist_ok=True)
        catalog_path = catalog_folder / f"{catalog_hash}.json"
        if not catalog_path.exists():
            shutil.copy2(self.players_path, catalog_path)
        return players, catalog_hash, catalog_path

    def _save_database(
        self,
        *,
        database_path: Path,
        run_id: str,
        snapshot_type: str,
        captured_at: str,
        league_id: str,
        season: str,
        season_type: str,
        week: int,
        run_folder: Path,
        catalog_hash: str,
        league_data: dict[str, Any],
        scoring_settings: dict[str, Any],
        users: list[dict[str, Any]],
        rosters: list[dict[str, Any]],
        matchups: list[dict[str, Any]],
        schedule: list[dict[str, Any]],
        players: dict[str, dict[str, Any]],
        stats_by_player: dict[str, dict[str, Any]],
        stat_type: str,
        provider: str,
        artifacts: dict[str, Path],
    ) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT INTO snapshot_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    snapshot_type,
                    captured_at,
                    league_id,
                    season,
                    season_type,
                    week,
                    str(run_folder.relative_to(self.storage_dir)),
                    catalog_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO league_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    league_id,
                    league_data.get("name"),
                    league_data.get("status"),
                    season,
                    season_type,
                    _json_text(league_data.get("settings") or {}),
                    _json_text(scoring_settings),
                    _json_text(league_data.get("roster_positions") or []),
                ),
            )
            self._save_scoring_settings(connection, run_id, scoring_settings)
            self._save_users(connection, run_id, users)
            self._save_rosters(connection, run_id, rosters)
            self._save_matchups(connection, run_id, matchups)
            self._save_schedule(connection, run_id, week, schedule)
            self._save_stats(
                connection,
                run_id,
                captured_at,
                players,
                stats_by_player,
                scoring_settings,
                stat_type,
                provider,
            )
            connection.executemany(
                "INSERT INTO snapshot_artifacts VALUES (?, ?, ?, ?)",
                [
                    (
                        run_id,
                        name,
                        str(path.relative_to(self.storage_dir)),
                        _sha256(path),
                    )
                    for name, path in artifacts.items()
                ],
            )

    @staticmethod
    def _save_scoring_settings(
        connection: sqlite3.Connection,
        run_id: str,
        scoring_settings: dict[str, Any],
    ) -> None:
        connection.executemany(
            "INSERT INTO scoring_setting_snapshots VALUES (?, ?, ?)",
            [
                (run_id, name, float(value))
                for name, value in scoring_settings.items()
                if isinstance(value, (int, float))
            ],
        )

    @staticmethod
    def _save_users(
        connection: sqlite3.Connection,
        run_id: str,
        users: list[dict[str, Any]],
    ) -> None:
        connection.executemany(
            "INSERT INTO league_user_snapshots VALUES (?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    str(user.get("user_id")),
                    user.get("display_name"),
                    (user.get("metadata") or {}).get("team_name"),
                    user.get("avatar"),
                )
                for user in users
                if user.get("user_id") is not None
            ],
        )

    @staticmethod
    def _save_rosters(
        connection: sqlite3.Connection,
        run_id: str,
        rosters: list[dict[str, Any]],
    ) -> None:
        roster_rows: list[tuple[Any, ...]] = []
        player_rows: list[tuple[Any, ...]] = []
        for roster in rosters:
            roster_id = int(roster.get("roster_id") or 0)
            settings = roster.get("settings") or {}
            roster_rows.append(
                (
                    run_id,
                    roster_id,
                    roster.get("owner_id"),
                    int(settings.get("wins") or 0),
                    int(settings.get("losses") or 0),
                    int(settings.get("ties") or 0),
                    _points_from_settings(settings, "fpts"),
                    _points_from_settings(settings, "fpts_against"),
                    _json_text(settings),
                )
            )
            starters = {str(player) for player in roster.get("starters") or []}
            reserves = {str(player) for player in roster.get("reserve") or []}
            for player_id in roster.get("players") or []:
                normalized_id = str(player_id)
                status = (
                    "starter"
                    if normalized_id in starters
                    else "reserve"
                    if normalized_id in reserves
                    else "bench"
                )
                player_rows.append((run_id, roster_id, normalized_id, status))
        connection.executemany(
            "INSERT INTO roster_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            roster_rows,
        )
        connection.executemany(
            "INSERT INTO roster_player_snapshots VALUES (?, ?, ?, ?)",
            player_rows,
        )

    @staticmethod
    def _save_matchups(
        connection: sqlite3.Connection,
        run_id: str,
        matchups: list[dict[str, Any]],
    ) -> None:
        matchup_rows: list[tuple[Any, ...]] = []
        player_rows: list[tuple[Any, ...]] = []
        for matchup in matchups:
            roster_id = int(matchup.get("roster_id") or 0)
            matchup_rows.append(
                (
                    run_id,
                    roster_id,
                    matchup.get("matchup_id"),
                    _numeric(matchup.get("points")),
                    matchup.get("custom_points"),
                )
            )
            starters = {
                str(player) for player in matchup.get("starters") or []
            }
            points = matchup.get("players_points") or {}
            for player_id in matchup.get("players") or []:
                normalized_id = str(player_id)
                player_rows.append(
                    (
                        run_id,
                        roster_id,
                        normalized_id,
                        int(normalized_id in starters),
                        _numeric(points.get(normalized_id)),
                    )
                )
        connection.executemany(
            "INSERT INTO matchup_snapshots VALUES (?, ?, ?, ?, ?)",
            matchup_rows,
        )
        connection.executemany(
            "INSERT INTO matchup_player_snapshots VALUES (?, ?, ?, ?, ?)",
            player_rows,
        )

    @staticmethod
    def _save_schedule(
        connection: sqlite3.Connection,
        run_id: str,
        selected_week: int,
        schedule: list[dict[str, Any]],
    ) -> None:
        rows = []
        for index, game in enumerate(schedule):
            if int(game.get("week") or 0) != selected_week:
                continue
            rows.append(
                (
                    run_id,
                    _game_key(game, index),
                    game.get("home") or game.get("home_team"),
                    game.get("away") or game.get("away_team"),
                    game.get("date")
                    or game.get("start_time")
                    or game.get("kickoff"),
                    game.get("status"),
                    _json_text(game),
                )
            )
        connection.executemany(
            "INSERT INTO game_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    @staticmethod
    def _save_stats(
        connection: sqlite3.Connection,
        run_id: str,
        captured_at: str,
        players: dict[str, dict[str, Any]],
        stats_by_player: dict[str, dict[str, Any]],
        scoring_settings: dict[str, Any],
        stat_type: str,
        provider: str,
    ) -> None:
        player_rows: list[tuple[Any, ...]] = []
        stat_rows: list[tuple[Any, ...]] = []
        value_rows: list[tuple[Any, ...]] = []
        for player_id, stats in stats_by_player.items():
            if not isinstance(stats, dict):
                continue
            player = players.get(str(player_id), {})
            player_rows.append(
                (
                    str(player_id),
                    player.get("first_name"),
                    player.get("last_name"),
                    player.get("position"),
                    player.get("team"),
                    str(player.get("espn_id"))
                    if player.get("espn_id") is not None
                    else None,
                    captured_at,
                )
            )
            stat_rows.append(
                (
                    run_id,
                    str(player_id),
                    stat_type,
                    provider,
                    calculate_fantasy_points(stats, scoring_settings),
                    _json_text(stats),
                )
            )
            value_rows.extend(
                (
                    run_id,
                    str(player_id),
                    stat_type,
                    provider,
                    stat_name,
                    float(stat_value),
                )
                for stat_name, stat_value in stats.items()
                if isinstance(stat_value, (int, float))
            )
        connection.executemany(
            """
            INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                position=excluded.position,
                team=excluded.team,
                espn_id=excluded.espn_id,
                updated_at=excluded.updated_at
            """,
            player_rows,
        )
        connection.executemany(
            "INSERT INTO player_stat_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            stat_rows,
        )
        connection.executemany(
            "INSERT INTO player_stat_values VALUES (?, ?, ?, ?, ?, ?)",
            value_rows,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive fantasy data to JSON and SQLite."
    )
    parser.add_argument(
        "snapshot_type",
        choices=("pre-kickoff", "post-week"),
        help="Capture projections before games or actual statistics afterward.",
    )
    parser.add_argument("--league-id", required=True)
    parser.add_argument("--week", required=True, type=int)
    parser.add_argument(
        "--season",
        help="Defaults to the season reported by the selected league.",
    )
    parser.add_argument(
        "--season-type",
        choices=("pre", "regular", "post"),
        help="Defaults to the season type reported by the selected league.",
    )
    parser.add_argument(
        "--storage-dir",
        type=Path,
        default=SNAPSHOT_STORAGE_DIR,
        help=f"Archive and database directory (default: {SNAPSHOT_STORAGE_DIR}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        result = SnapshotCollector(storage_dir=arguments.storage_dir).collect(
            snapshot_type=arguments.snapshot_type,
            league_id=arguments.league_id,
            week=arguments.week,
            season=arguments.season,
            season_type=arguments.season_type,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        requests.RequestException,
        sqlite3.Error,
    ) as error:
        print(f"Snapshot failed: {error}", file=sys.stderr)
        return 1

    print(f"Snapshot {result.run_id} completed.")
    print(f"Archive: {result.archive_path}")
    print(f"Database: {result.database_path}")
    print(f"Player stat records: {result.player_stat_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
