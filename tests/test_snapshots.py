import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from fantasy_dashboard.snapshots import SnapshotCollector


class FakeSleeperClient:
    def get_raw_api_data(self, endpoint: str) -> dict[str, Any] | list[Any]:
        responses: dict[str, dict[str, Any] | list[Any]] = {
            "league/league-1": {
                "league_id": "league-1",
                "name": "Test League",
                "status": "in_season",
                "season": "2026",
                "season_type": "regular",
                "settings": {"num_teams": 2},
                "scoring_settings": {"pass_yd": 0.04, "pass_td": 4},
                "roster_positions": ["QB", "BN"],
            },
            "league/league-1/users": [
                {
                    "user_id": "user-1",
                    "display_name": "Owner",
                    "avatar": "avatar-1",
                    "metadata": {"team_name": "Test Team"},
                }
            ],
            "league/league-1/rosters": [
                {
                    "roster_id": 1,
                    "owner_id": "user-1",
                    "players": ["player-1", "player-2"],
                    "starters": ["player-1"],
                    "reserve": [],
                    "settings": {
                        "wins": 1,
                        "losses": 0,
                        "ties": 0,
                        "fpts": 100,
                        "fpts_decimal": 25,
                        "fpts_against": 90,
                    },
                }
            ],
            "league/league-1/matchups/1": [
                {
                    "roster_id": 1,
                    "matchup_id": 1,
                    "points": 14,
                    "players": ["player-1", "player-2"],
                    "starters": ["player-1"],
                    "players_points": {"player-1": 14},
                }
            ],
        }
        return responses[endpoint]

    def get_nfl_state(self) -> dict[str, Any]:
        return {"season": "2026", "week": 1, "season_type": "regular"}

    def get_nfl_schedule(self, season: str, season_type: str) -> list[dict[str, Any]]:
        return [
            {
                "game_id": "game-1",
                "week": 1,
                "home": "BUF",
                "away": "NYJ",
                "date": "2026-09-10T20:20:00Z",
                "status": "scheduled",
            }
        ]

    def get_player_stats(
        self, season: str, season_type: str, week: int
    ) -> dict[str, dict[str, float]]:
        return {"player-1": {"pass_yd": 250, "pass_td": 2}}

    def refresh_nfl_players_cache(self, cache_path: Path) -> bool:
        return False


class FakeEspnClient:
    def get_nfl_schedule(
        self, season: str, week: int, season_type: str
    ) -> dict[str, Any]:
        return {
            "events": [
                {
                    "id": "espn-game-1",
                    "date": "2026-09-10T20:20:00Z",
                    "status": {"type": {"name": "STATUS_SCHEDULED"}},
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"abbreviation": "BUF"},
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"abbreviation": "NYJ"},
                                },
                            ]
                        }
                    ],
                }
            ]
        }

    def get_nfl_projections(self, season: str, cache_path: Path) -> dict[str, Any]:
        data = {
            "players": [
                {
                    "player": {
                        "id": 123,
                        "fullName": "Test Quarterback",
                        "defaultPositionId": 1,
                        "stats": [
                            {
                                "seasonId": 2026,
                                "statSourceId": 1,
                                "statSplitTypeId": 1,
                                "scoringPeriodId": 1,
                                "stats": {"3": 250, "4": 1},
                            }
                        ],
                    }
                }
            ]
        }
        cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data


@pytest.fixture
def players_path(tmp_path: Path) -> Path:
    path = tmp_path / "nfl_players.json"
    path.write_text(
        json.dumps(
            {
                "player-1": {
                    "espn_id": 123,
                    "first_name": "Test",
                    "last_name": "Quarterback",
                    "position": "QB",
                    "team": "BUF",
                },
                "player-2": {
                    "first_name": "Bench",
                    "last_name": "Player",
                    "position": "QB",
                    "team": "NYJ",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _collector(tmp_path: Path, players_path: Path) -> SnapshotCollector:
    return SnapshotCollector(
        storage_dir=tmp_path / "storage",
        players_path=players_path,
        sleeper_client=FakeSleeperClient(),
        espn_client=FakeEspnClient(),
    )


def test_pre_kickoff_snapshot_archives_and_normalizes_projections(
    tmp_path: Path, players_path: Path
) -> None:
    result = _collector(tmp_path, players_path).collect("pre-kickoff", "league-1", 1)

    assert (result.archive_path / "manifest.json").exists()
    assert (result.archive_path / "espn_projections.json").exists()
    assert (result.archive_path / "scoring_settings.json").exists()
    assert result.player_stat_count == 1

    with sqlite3.connect(result.database_path) as connection:
        run = connection.execute(
            "SELECT snapshot_type, season, week FROM snapshot_runs"
        ).fetchone()
        stat = connection.execute("""
            SELECT stat_type, provider, fantasy_points
            FROM player_stat_snapshots
            """).fetchone()
        statuses = connection.execute("""
            SELECT player_id, roster_status
            FROM roster_player_snapshots ORDER BY player_id
            """).fetchall()
        game = connection.execute("""
            SELECT game_key, kickoff_at, provider FROM game_snapshots
            """).fetchone()
        identity = connection.execute("""
            SELECT player_id, nfl_team, game_key
            FROM player_identity_snapshots WHERE player_id = 'player-1'
            """).fetchone()
        stat_link = connection.execute("""
            SELECT nfl_team, game_key FROM player_stat_snapshots
            """).fetchone()

    assert run == ("pre-kickoff", "2026", 1)
    assert stat == ("projection", "espn", 14.0)
    assert statuses == [("player-1", "starter"), ("player-2", "bench")]
    assert game == ("espn-game-1", "2026-09-10T20:20:00Z", "espn")
    assert identity == ("player-1", "BUF", "espn-game-1")
    assert stat_link == ("BUF", "espn-game-1")
    assert (result.archive_path / "espn_schedule.json").exists()


def test_post_week_snapshot_archives_actual_statistics(
    tmp_path: Path, players_path: Path
) -> None:
    result = _collector(tmp_path, players_path).collect("post-week", "league-1", 1)

    actual_path = result.archive_path / "sleeper_player_stats.json"
    assert json.loads(actual_path.read_text(encoding="utf-8")) == {
        "player-1": {"pass_td": 2, "pass_yd": 250}
    }

    with sqlite3.connect(result.database_path) as connection:
        stat = connection.execute("""
            SELECT stat_type, provider, fantasy_points
            FROM player_stat_snapshots
            """).fetchone()
        scoring = connection.execute("""
            SELECT stat_name, points FROM scoring_setting_snapshots
            ORDER BY stat_name
            """).fetchall()

    assert stat == ("actual", "sleeper", 18.0)
    assert scoring == [("pass_td", 4.0), ("pass_yd", 0.04)]


def test_existing_database_receives_additive_snapshot_migrations(
    tmp_path: Path, players_path: Path
) -> None:
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    database_path = storage_dir / "fantasy_dashboard.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("""
            CREATE TABLE player_stat_snapshots (
                run_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                stat_type TEXT NOT NULL,
                provider TEXT NOT NULL,
                fantasy_points REAL NOT NULL,
                stats_json TEXT NOT NULL,
                PRIMARY KEY (run_id, player_id, stat_type, provider)
            )
            """)
        connection.execute("""
            CREATE TABLE game_snapshots (
                run_id TEXT NOT NULL,
                game_key TEXT NOT NULL,
                home_team TEXT,
                away_team TEXT,
                kickoff_at TEXT,
                status TEXT,
                game_json TEXT NOT NULL,
                PRIMARY KEY (run_id, game_key)
            )
            """)

    collector = SnapshotCollector(
        storage_dir=storage_dir,
        players_path=players_path,
        sleeper_client=FakeSleeperClient(),
        espn_client=FakeEspnClient(),
    )
    collector.collect("pre-kickoff", "league-1", 1)

    with sqlite3.connect(database_path) as connection:
        stat_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(player_stat_snapshots)")
        }
        game_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(game_snapshots)")
        }
        identity_count = connection.execute(
            "SELECT COUNT(*) FROM player_identity_snapshots"
        ).fetchone()[0]

    assert {"nfl_team", "game_key"}.issubset(stat_columns)
    assert "provider" in game_columns
    assert identity_count == 2
