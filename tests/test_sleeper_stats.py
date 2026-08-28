from fantasy_dashboard.clients import sleeper
from fantasy_dashboard.clients.sleeper import SleeperClient


class FakeResponse:
    def __init__(self, data: object) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._data


# Weekly stat requests should use the selected season type, season, and week.
def test_get_weekly_player_stats(monkeypatch) -> None:
    requested_urls: list[str] = []

    def fake_get(url: str, timeout: float) -> FakeResponse:
        requested_urls.append(url)
        assert timeout == 10.0
        return FakeResponse(
            {
                "player-1": {"pass_yd": 250},
                "invalid-player": None,
            }
        )

    monkeypatch.setattr(sleeper.requests, "get", fake_get)

    stats = SleeperClient().get_player_stats("2026", "regular", 4)

    assert requested_urls == ["https://api.sleeper.app/v1/stats/nfl/regular/2026/4"]
    assert stats == {"player-1": {"pass_yd": 250}}


# Omitting a week should request Sleeper's season aggregate endpoint.
def test_get_season_player_stats(monkeypatch) -> None:
    requested_urls: list[str] = []

    def fake_get(url: str, timeout: float) -> FakeResponse:
        requested_urls.append(url)
        return FakeResponse({})

    monkeypatch.setattr(sleeper.requests, "get", fake_get)

    stats = SleeperClient().get_player_stats("2026", "regular")

    assert requested_urls == ["https://api.sleeper.app/v1/stats/nfl/regular/2026"]
    assert stats == {}


def test_get_nfl_schedule_uses_season_endpoint(monkeypatch) -> None:
    requested_urls: list[str] = []

    def fake_get(url: str, timeout: float) -> FakeResponse:
        requested_urls.append(url)
        return FakeResponse([{"week": 1, "home": "KC", "away": "BUF"}, None])

    monkeypatch.setattr(sleeper.requests, "get", fake_get)

    schedule = SleeperClient().get_nfl_schedule("2026", "regular")

    assert requested_urls == ["https://api.sleeper.app/schedule/nfl/regular/2026"]
    assert schedule == [{"week": 1, "home": "KC", "away": "BUF"}]


def test_get_trending_players_uses_requested_window_and_limit(monkeypatch) -> None:
    request: dict[str, object] = {}

    def fake_get(url: str, params: dict[str, int], timeout: float) -> FakeResponse:
        request.update(url=url, params=params, timeout=timeout)
        return FakeResponse([{"player_id": "player-1", "count": 12}])

    monkeypatch.setattr(sleeper.requests, "get", fake_get)

    trends = SleeperClient().get_trending_players("add", 48, 25)

    assert request == {
        "url": "https://api.sleeper.app/v1/players/nfl/trending/add",
        "params": {"lookback_hours": 48, "limit": 25},
        "timeout": 10.0,
    }
    assert trends == [{"player_id": "player-1", "count": 12}]


def test_get_player_weekly_stats_normalizes_week_keys(monkeypatch) -> None:
    request: dict[str, object] = {}

    def fake_get(url: str, params: dict[str, str], timeout: float) -> FakeResponse:
        request.update(url=url, params=params, timeout=timeout)
        return FakeResponse(
            {
                "1": {
                    "week": 1,
                    "opponent": "BUF",
                    "stats": {"pass_yd": 250},
                },
                "2": None,
            }
        )

    monkeypatch.setattr(sleeper.requests, "get", fake_get)

    weekly_stats = SleeperClient().get_player_weekly_stats(
        "player-1", "2026", "regular"
    )

    assert request == {
        "url": "https://api.sleeper.com/stats/nfl/player/player-1",
        "params": {
            "season": "2026",
            "season_type": "regular",
            "grouping": "week",
        },
        "timeout": 10.0,
    }
    assert weekly_stats == {
        1: {"week": 1, "opponent": "BUF", "stats": {"pass_yd": 250}}
    }
