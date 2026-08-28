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

    def get_nfl_schedule(
        self, season: str, season_type: str
    ) -> list[dict[str, Any]]:
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
    def get_nfl_projections(
        self, season: str, cache_path: Path
    ) -> dict[str, Any]:
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
    result = _collector(tmp_path, players_path).collect(
        "pre-kickoff", "league-1", 1
    )

    assert (result.archive_path / "manifest.json").exists()
    assert (result.archive_path / "espn_projections.json").exists()
    assert (result.archive_path / "scoring_settings.json").exists()
    assert result.player_stat_count == 1

    with sqlite3.connect(result.database_path) as connection:
        run = connection.execute(
            "SELECT snapshot_type, season, week FROM snapshot_runs"
        ).fetchone()
        stat = connection.execute(
            """
            SELECT stat_type, provider, fantasy_points
            FROM player_stat_snapshots
            """
        ).fetchone()
        statuses = connection.execute(
            """
            SELECT player_id, roster_status
            FROM roster_player_snapshots ORDER BY player_id
            """
        ).fetchall()

    assert run == ("pre-kickoff", "2026", 1)
    assert stat == ("projection", "espn", 14.0)
    assert statuses == [("player-1", "starter"), ("player-2", "bench")]


def test_post_week_snapshot_archives_actual_statistics(
    tmp_path: Path, players_path: Path
) -> None:
    result = _collector(tmp_path, players_path).collect(
        "post-week", "league-1", 1
    )

    actual_path = result.archive_path / "sleeper_player_stats.json"
    assert json.loads(actual_path.read_text(encoding="utf-8")) == {
        "player-1": {"pass_td": 2, "pass_yd": 250}
    }

    with sqlite3.connect(result.database_path) as connection:
        stat = connection.execute(
            """
            SELECT stat_type, provider, fantasy_points
            FROM player_stat_snapshots
            """
        ).fetchone()
        scoring = connection.execute(
            """
            SELECT stat_name, points FROM scoring_setting_snapshots
            ORDER BY stat_name
            """
        ).fetchall()

    assert stat == ("actual", "sleeper", 18.0)
    assert scoring == [("pass_td", 4.0), ("pass_yd", 0.04)]
