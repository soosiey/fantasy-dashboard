import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import requests

from fantasy_dashboard import data
from fantasy_dashboard.models.matchup import WeeklyMatchupContainer


# A stateless API client must not survive a hot reload with stale model classes.
def test_sleeper_client_is_not_cached() -> None:
    assert data.get_sleeper_client() is not data.get_sleeper_client()


def test_prediction_matchup_schedules_are_batched_and_cached(monkeypatch) -> None:
    calls: list[int] = []

    class FakeClient:
        def get_matchups(self, league_id: str, week: int) -> WeeklyMatchupContainer:
            assert league_id == "league-1"
            calls.append(week)
            if week == 3:
                raise requests.RequestException("unavailable")
            return WeeklyMatchupContainer.from_api(
                [
                    {
                        "starters": [],
                        "players": [],
                        "roster_id": 1,
                        "matchup_id": week,
                        "points": 0,
                    }
                ]
            )

    data.get_weekly_matchup_schedules.clear()
    monkeypatch.setattr(data, "get_sleeper_client", FakeClient)

    schedules, unavailable = data.get_weekly_matchup_schedules("league-1", 1, 3)
    cached_schedules, cached_unavailable = data.get_weekly_matchup_schedules(
        "league-1", 1, 3
    )

    assert set(schedules) == {1, 2}
    assert unavailable == [3]
    assert set(cached_schedules) == {1, 2}
    assert cached_unavailable == [3]
    assert sorted(calls) == [1, 2, 3]


# The active NFL season and week should share one cached Sleeper state lookup.
def test_current_nfl_state_is_cached(monkeypatch) -> None:
    calls = 0
    nfl_state = {
        "season": "2026",
        "season_type": "regular",
        "week": 6,
        "display_week": 7,
    }

    class FakeClient:
        def get_nfl_state(self) -> dict[str, str | int]:
            nonlocal calls
            calls += 1
            return nfl_state.copy()

    data.get_nfl_state.clear()
    monkeypatch.setattr(data, "get_sleeper_client", FakeClient)

    assert data.get_current_nfl_season() == "2026"
    assert data.get_current_nfl_week() == 7
    assert data.get_default_nfl_week("2026") == 7
    assert data.get_default_nfl_week("2025") == 1
    assert calls == 1

    nfl_state["season_type"] = "pre"
    nfl_state["display_week"] = 3
    data.get_nfl_state.clear()

    assert data.get_default_nfl_week("2026") == 1
    assert calls == 2


# Repeated lookups should be reused until a targeted force refresh clears them.
def test_league_lookup_is_cached_and_can_be_refreshed(monkeypatch) -> None:
    calls: list[str] = []

    class FakeClient:
        def get_single_league(self, league_id: str) -> SimpleNamespace:
            calls.append(league_id)
            return SimpleNamespace(league_id=league_id)

    data.get_league.clear()
    monkeypatch.setattr(data, "get_sleeper_client", FakeClient)

    first = data.get_league("league-1")
    second = data.get_league("league-1")
    cached_update = data.get_data_update("league", "league-1")

    assert first.league_id == "league-1"
    assert second.league_id == "league-1"
    assert calls == ["league-1"]
    assert cached_update is not None
    assert cached_update.provider == "Sleeper"

    data.clear_league_data("league-1")
    refreshed = data.get_league("league-1")
    refreshed_update = data.get_data_update("league", "league-1")

    assert refreshed.league_id == "league-1"
    assert calls == ["league-1", "league-1"]
    assert refreshed_update is not None
    assert refreshed_update.updated_at >= cached_update.updated_at


# A new file modification version should replace the cached decoded player data.
def test_player_cache_invalidates_for_new_file_version(tmp_path) -> None:
    player_path = tmp_path / "players.json"
    data._load_nfl_players.clear()

    player_path.write_text(json.dumps({"1": {"first_name": "First"}}))
    first = data._load_nfl_players(str(player_path), 1)

    player_path.write_text(json.dumps({"2": {"first_name": "Second"}}))
    second = data._load_nfl_players(str(player_path), 2)

    assert first == {"1": {"first_name": "First"}}
    assert second == {"2": {"first_name": "Second"}}


# A failed initial player download should leave pages with a safe empty mapping.
def test_missing_player_cache_returns_empty_mapping(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(data, "NFL_PLAYERS_PATH", tmp_path / "missing.json")

    assert data.get_nfl_players() == {}


def test_player_stats_reuse_persistent_week_cache(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, str, int | None]] = []
    provider_stats = {"player-1": {"pass_yd": 250}}

    class FakeClient:
        def get_player_stats(
            self,
            season: str,
            season_type: str,
            week: int | None,
        ) -> dict[str, dict]:
            calls.append((season, season_type, week))
            return provider_stats.copy()

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(data, "get_sleeper_client", FakeClient)
    data._read_json_cache.clear()

    assert data.get_player_stats("2026", "regular", 4) == provider_stats
    provider_stats["player-1"] = {"pass_yd": 300}
    assert data.get_player_stats("2026", "regular", 4) == {"player-1": {"pass_yd": 250}}
    assert calls == [("2026", "regular", 4)]

    data.refresh_player_stats_cache("2026", "regular", 4)
    assert data.get_player_stats("2026", "regular", 4) == {"player-1": {"pass_yd": 300}}
    assert calls == [("2026", "regular", 4), ("2026", "regular", 4)]


def test_player_game_log_uses_refreshed_bulk_week(monkeypatch, tmp_path) -> None:
    calls = 0

    class FakeClient:
        def get_player_weekly_stats(
            self,
            player_id: str,
            season: str,
            season_type: str,
        ) -> dict[int, dict]:
            nonlocal calls
            calls += 1
            return {
                1: {
                    "week": 1,
                    "opponent": "NYJ",
                    "stats": {"pass_yd": 250},
                }
            }

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(data, "get_sleeper_client", FakeClient)
    data._read_json_cache.clear()

    initial = data.get_player_weekly_stats("player-1", "2026", "regular")
    assert initial[1]["stats"] == {"pass_yd": 250}

    week_path = data._stats_cache_path("sleeper", "2026", "regular", 1)
    data._write_json_cache(week_path, {"player-1": {"pass_yd": 300}})
    data._read_json_cache.clear()
    refreshed = data.get_player_weekly_stats("player-1", "2026", "regular")

    assert refreshed[1] == {
        "week": 1,
        "opponent": "NYJ",
        "stats": {"pass_yd": 300},
    }
    assert calls == 1


def test_projected_stats_reuse_normalized_week_cache(monkeypatch, tmp_path) -> None:
    provider_calls = 0
    mapping_calls = 0

    class FakeEspnClient:
        def get_nfl_projections(self, *args, **kwargs) -> dict:
            nonlocal provider_calls
            provider_calls += 1
            return {"players": []}

    def map_projections(*args, **kwargs) -> dict[str, dict[str, float]]:
        nonlocal mapping_calls
        mapping_calls += 1
        return {"player-1": {"pass_yd": 275.0}}

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(data, "ESPN_PROJECTIONS_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(data, "EspnClient", FakeEspnClient)
    monkeypatch.setattr(data, "map_projections_to_sleeper", map_projections)
    monkeypatch.setattr(data, "get_nfl_players", dict)
    data._read_json_cache.clear()

    first = data.get_projected_player_stats("2026", 4)
    second = data.get_projected_player_stats("2026", 4)

    assert first == {"player-1": {"pass_yd": 275.0}}
    assert second == first
    assert provider_calls == 1
    assert mapping_calls == 1


def test_empty_normalized_projection_cache_is_rebuilt_from_saved_raw_data(
    monkeypatch,
    tmp_path,
) -> None:
    raw_path = tmp_path / "raw" / "2026.json"
    normalized_path = tmp_path / "weekly" / "espn" / "2026" / "regular" / "week_4.json"
    raw_path.parent.mkdir(parents=True)
    normalized_path.parent.mkdir(parents=True)
    raw_path.write_text('{"players": [{"player": {"id": 1}}]}')
    normalized_path.write_text("{}")
    requested_max_ages: list[timedelta] = []

    class FakeEspnClient:
        def get_nfl_projections(
            self,
            season: str,
            cache_path,
            *,
            max_age: timedelta,
        ) -> dict:
            requested_max_ages.append(max_age)
            return {"players": [{"player": {"id": 1}}]}

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(data, "ESPN_PROJECTIONS_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(data, "EspnClient", FakeEspnClient)
    monkeypatch.setattr(
        data,
        "map_projections_to_sleeper",
        lambda *args: {"player-1": {"pass_yd": 275.0}},
    )
    monkeypatch.setattr(data, "get_nfl_players", dict)
    data._read_json_cache.clear()

    stats = data.get_projected_player_stats("2026", 4)

    assert stats == {"player-1": {"pass_yd": 275.0}}
    assert requested_max_ages == [data.CURRENT_PROJECTION_CACHE_MAX_AGE]
    assert json.loads(normalized_path.read_text()) == stats


def test_empty_projection_caches_force_an_immediate_espn_request(
    monkeypatch,
    tmp_path,
) -> None:
    raw_path = tmp_path / "raw" / "2026.json"
    normalized_path = tmp_path / "weekly" / "espn" / "2026" / "regular" / "week_4.json"
    raw_path.parent.mkdir(parents=True)
    normalized_path.parent.mkdir(parents=True)
    raw_path.write_text('{"players": []}')
    normalized_path.write_text("{}")
    requested_max_ages: list[timedelta] = []

    class FakeEspnClient:
        def get_nfl_projections(
            self,
            season: str,
            cache_path,
            *,
            max_age: timedelta,
        ) -> dict:
            requested_max_ages.append(max_age)
            return {"players": [{"player": {"id": 1}}]}

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(data, "ESPN_PROJECTIONS_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(data, "EspnClient", FakeEspnClient)
    monkeypatch.setattr(
        data,
        "map_projections_to_sleeper",
        lambda *args: {"player-1": {"pass_yd": 275.0}},
    )
    monkeypatch.setattr(data, "get_nfl_players", dict)
    data._read_json_cache.clear()

    assert data.get_projected_player_stats("2026", 4) == {
        "player-1": {"pass_yd": 275.0}
    }
    assert requested_max_ages == [timedelta(0)]


def test_empty_projection_refresh_preserves_last_usable_normalized_cache(
    monkeypatch,
    tmp_path,
) -> None:
    normalized_path = tmp_path / "weekly" / "espn" / "2026" / "regular" / "week_4.json"
    normalized_path.parent.mkdir(parents=True)
    saved_stats = {"player-1": {"pass_yd": 250.0}}
    normalized_path.write_text(json.dumps(saved_stats))

    class FakeEspnClient:
        def get_nfl_projections(self, *args, **kwargs) -> dict:
            return {"players": []}

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(data, "ESPN_PROJECTIONS_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(data, "EspnClient", FakeEspnClient)
    monkeypatch.setattr(data, "map_projections_to_sleeper", lambda *args: {})
    monkeypatch.setattr(data, "get_nfl_players", dict)
    data._read_json_cache.clear()

    stats = data.refresh_projected_player_stats_cache(
        "2026",
        4,
        force_provider=True,
    )

    assert stats == saved_stats
    assert json.loads(normalized_path.read_text()) == saved_stats


def test_projected_stats_report_raw_espn_refresh_and_rebuild_stale_normalized_cache(
    monkeypatch,
    tmp_path,
) -> None:
    raw_path = tmp_path / "raw" / "2026.json"
    normalized_path = tmp_path / "weekly" / "espn" / "2026" / "regular" / "week_4.json"
    raw_path.parent.mkdir(parents=True)
    normalized_path.parent.mkdir(parents=True)
    raw_path.write_text('{"players": []}')
    normalized_path.write_text('{"player-1": {"pass_yd": 200}}')
    normalized_time = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    raw_time = datetime(2026, 8, 31, 18, 0, tzinfo=timezone.utc)
    os.utime(
        normalized_path,
        (normalized_time.timestamp(), normalized_time.timestamp()),
    )
    os.utime(raw_path, (raw_time.timestamp(), raw_time.timestamp()))
    mapping_calls = 0

    class FakeEspnClient:
        def get_nfl_projections(self, *args, **kwargs) -> dict:
            return {"players": []}

    def map_projections(*args, **kwargs) -> dict[str, dict[str, float]]:
        nonlocal mapping_calls
        mapping_calls += 1
        return {"player-1": {"pass_yd": 275.0}}

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(data, "ESPN_PROJECTIONS_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(data, "EspnClient", FakeEspnClient)
    monkeypatch.setattr(data, "map_projections_to_sleeper", map_projections)
    monkeypatch.setattr(data, "get_nfl_players", dict)
    data._read_json_cache.clear()

    stats = data.get_projected_player_stats("2026", 4)
    update = data.get_data_update("projected_player_stats", "2026", 4)

    assert stats == {"player-1": {"pass_yd": 275.0}}
    assert mapping_calls == 1
    assert update is not None
    assert update.updated_at == raw_time


def test_projection_refresh_uses_six_hour_raw_espn_cache(
    monkeypatch,
    tmp_path,
) -> None:
    requested_max_ages: list[timedelta] = []

    class FakeEspnClient:
        def get_nfl_projections(
            self,
            season: str,
            cache_path,
            *,
            max_age: timedelta,
        ) -> dict:
            assert season == "2026"
            assert cache_path == tmp_path / "raw" / "2026.json"
            requested_max_ages.append(max_age)
            return {"players": []}

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(data, "ESPN_PROJECTIONS_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(data, "EspnClient", FakeEspnClient)
    monkeypatch.setattr(data, "map_projections_to_sleeper", lambda *args: {})
    monkeypatch.setattr(data, "get_nfl_players", dict)

    data.refresh_projected_player_stats_cache("2026", 4)

    assert requested_max_ages == [data.CURRENT_PROJECTION_CACHE_MAX_AGE]


def test_pregame_projection_update_uses_authoritative_refresh_function(
    monkeypatch,
    tmp_path,
) -> None:
    refreshes: list[tuple[str, int | None, timedelta]] = []

    monkeypatch.setattr(data, "WEEKLY_STATS_CACHE_DIR", tmp_path / "weekly")
    monkeypatch.setattr(
        data,
        "get_nfl_state",
        lambda: {
            "season": "2026",
            "season_type": "regular",
            "week": 4,
            "display_week": 4,
        },
    )
    monkeypatch.setattr(
        data,
        "get_nfl_schedule",
        lambda *args: [{"week": 4, "status": "pre_game"}],
    )
    monkeypatch.setattr(data, "refresh_player_stats_cache", lambda *args: {})

    def refresh_projections(
        season: str,
        week: int | None,
        *,
        force_provider: bool = False,
        raw_cache_max_age: timedelta,
    ) -> dict[str, dict[str, float]]:
        assert not force_provider
        refreshes.append((season, week, raw_cache_max_age))
        return {}

    monkeypatch.setattr(
        data,
        "refresh_projected_player_stats_cache",
        refresh_projections,
    )

    data.refresh_current_week_input_data()

    assert refreshes == [
        ("2026", 4, data.CURRENT_PROJECTION_CACHE_MAX_AGE),
        ("2026", None, data.CURRENT_PROJECTION_CACHE_MAX_AGE),
    ]


def test_actual_cache_uses_live_and_finalized_refresh_windows(tmp_path) -> None:
    cache_path = tmp_path / "week_1.json"
    cache_path.write_text("{}")
    checked_at = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
    live_games = [{"date": "2026-09-14", "status": "in_progress"}]

    recent_live_update = checked_at.timestamp() - 30
    os.utime(cache_path, (recent_live_update, recent_live_update))
    assert not data._actual_cache_needs_refresh(
        cache_path,
        live_games,
        now=checked_at,
    )

    stale_live_update = checked_at.timestamp() - 61
    os.utime(cache_path, (stale_live_update, stale_live_update))
    assert data._actual_cache_needs_refresh(
        cache_path,
        live_games,
        now=checked_at,
    )

    pregame_games = [{"date": "2026-09-14", "status": "pre_game"}]
    hourly_update = checked_at.timestamp() - 3600
    os.utime(cache_path, (hourly_update, hourly_update))
    assert not data._actual_cache_needs_refresh(
        cache_path,
        pregame_games,
        now=checked_at,
    )

    daily_update = checked_at.timestamp() - 86400
    os.utime(cache_path, (daily_update, daily_update))
    assert data._actual_cache_needs_refresh(
        cache_path,
        pregame_games,
        now=checked_at,
    )

    completed_games = [{"date": "2026-09-07", "status": "complete"}]
    before_deadline = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(cache_path, (before_deadline, before_deadline))
    assert not data._actual_cache_needs_refresh(
        cache_path,
        completed_games,
        now=datetime(2026, 9, 9, 13, 0, tzinfo=timezone.utc),
    )

    stale_final_update = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(cache_path, (stale_final_update, stale_final_update))
    after_deadline = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    assert data._actual_cache_needs_refresh(
        cache_path,
        completed_games,
        now=after_deadline,
    )

    finalized_update = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc).timestamp()
    os.utime(cache_path, (finalized_update, finalized_update))
    assert not data._actual_cache_needs_refresh(
        cache_path,
        completed_games,
        now=checked_at,
    )


def test_projection_cache_is_six_hourly_except_when_a_game_is_live() -> None:
    assert data.CURRENT_PROJECTION_CACHE_MAX_AGE.total_seconds() == 6 * 60 * 60
    assert data._projection_cache_max_age([]) == data.CURRENT_PROJECTION_CACHE_MAX_AGE
    assert (
        data._projection_cache_max_age([{"status": "pre_game"}, {"status": "complete"}])
        == data.CURRENT_PROJECTION_CACHE_MAX_AGE
    )
    assert (
        data._projection_cache_max_age(
            [{"status": "complete"}, {"status": "in_progress"}]
        )
        == data.LIVE_PROJECTION_CACHE_MAX_AGE
    )


def test_manual_refresh_cooldown_persists_for_six_hours(
    monkeypatch,
    tmp_path,
) -> None:
    state_path = tmp_path / "manual_refresh.json"
    monkeypatch.setattr(data, "MANUAL_REFRESH_STATE_PATH", state_path)
    data._read_json_cache.clear()
    refreshed_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    assert data.get_manual_refresh_cooldown_remaining(now=refreshed_at) == timedelta(0)

    data.record_manual_refresh(refreshed_at=refreshed_at)
    assert data.get_manual_refresh_cooldown_remaining(
        now=refreshed_at + timedelta(hours=1)
    ) == timedelta(hours=5)
    assert data.get_manual_refresh_cooldown_remaining(
        now=refreshed_at + timedelta(hours=6)
    ) == timedelta(0)
