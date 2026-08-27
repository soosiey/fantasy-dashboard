import json
from types import SimpleNamespace

from fantasy_dashboard import data


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

    assert first.league_id == "league-1"
    assert second.league_id == "league-1"
    assert calls == ["league-1"]

    data.clear_league_data("league-1")
    refreshed = data.get_league("league-1")

    assert refreshed.league_id == "league-1"
    assert calls == ["league-1", "league-1"]


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
