import json
from types import SimpleNamespace

from fantasy_dashboard import data


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
