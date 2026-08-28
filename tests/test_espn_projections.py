import json

from fantasy_dashboard.clients import espn
from fantasy_dashboard.clients.espn import (
    EspnClient,
    map_projections_to_sleeper,
)


class FakeResponse:
    def __init__(self, data: object) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._data


# One ESPN response should populate the disk cache shared by all periods.
def test_projection_request_fetches_all_players_and_reuses_disk_cache(
    monkeypatch, tmp_path
) -> None:
    requests: list[dict[str, object]] = []
    response_data = {"players": [{"player": {"id": 1}}]}

    def fake_get(
        url: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        requests.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(response_data)

    monkeypatch.setattr(espn.requests, "get", fake_get)
    cache_path = tmp_path / "projections.json"

    first = EspnClient().get_nfl_projections("2026", cache_path)
    second = EspnClient().get_nfl_projections("2026", cache_path)

    assert first == response_data
    assert second == response_data
    assert len(requests) == 1
    assert requests[0]["url"].endswith("/seasons/2026/segments/0/leaguedefaults/1")
    assert requests[0]["params"] == {"view": "kona_player_info"}
    assert (
        json.loads(requests[0]["headers"]["x-fantasy-filter"])["players"]["limit"]
        == 5000
    )


def test_schedule_request_selects_regular_week_and_exact_events(
    monkeypatch,
) -> None:
    requests: list[dict[str, object]] = []
    response_data = {"events": [{"id": "game-1", "date": "2026-09-10T20:20:00Z"}]}

    def fake_get(
        url: str,
        params: dict[str, str | int],
        timeout: float,
    ) -> FakeResponse:
        requests.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(response_data)

    monkeypatch.setattr(espn.requests, "get", fake_get)

    result = EspnClient().get_nfl_schedule("2026", 1, "regular")

    assert result == response_data
    assert requests == [
        {
            "url": EspnClient.SCOREBOARD_URL,
            "params": {
                "dates": "2026",
                "seasontype": 2,
                "week": 1,
                "limit": 100,
            },
            "timeout": 30.0,
        }
    ]


# ESPN IDs and raw stat IDs should become Sleeper player and scoring keys.
def test_weekly_projections_map_to_sleeper_ids_and_stat_names() -> None:
    sleeper_players = {
        "player-1": {
            "espn_id": 123,
            "first_name": "Josh",
            "last_name": "Allen",
            "position": "QB",
        },
        "BUF": {
            "espn_id": None,
            "first_name": "Buffalo",
            "last_name": "Bills",
            "position": "DEF",
        },
    }
    projection_data = {
        "players": [
            {
                "player": {
                    "id": 123,
                    "fullName": "Josh Allen",
                    "defaultPositionId": 1,
                    "stats": [
                        {
                            "seasonId": 2025,
                            "statSourceId": 1,
                            "statSplitTypeId": 1,
                            "scoringPeriodId": 1,
                            "stats": {"3": 250, "4": 2},
                        },
                        {
                            "seasonId": 2026,
                            "statSourceId": 1,
                            "statSplitTypeId": 1,
                            "scoringPeriodId": 1,
                            "stats": {"3": 275.5, "4": 2.1, "20": 0.7},
                        },
                    ],
                }
            },
            {
                "player": {
                    "id": 999,
                    "fullName": "Bills D/ST",
                    "defaultPositionId": 16,
                    "proTeamId": 2,
                    "stats": [
                        {
                            "seasonId": 2026,
                            "statSourceId": 1,
                            "statSplitTypeId": 1,
                            "scoringPeriodId": 1,
                            "stats": {
                                "89": 0.1,
                                "92": 0.3,
                                "95": 1.2,
                                "99": 2.5,
                                "121": 0.2,
                            },
                        }
                    ],
                }
            },
        ]
    }

    mapped = map_projections_to_sleeper(projection_data, sleeper_players, "2026", 1)

    assert mapped == {
        "player-1": {"pass_yd": 275.5, "pass_td": 2.1, "pass_int": 0.7},
        "BUF": {
            "pts_allow_0": 0.1,
            "pts_allow_14_20": 0.5,
            "int": 1.2,
            "sack": 2.5,
        },
    }


# Season mode must select ESPN's season aggregate instead of a weekly record.
def test_season_projection_uses_current_season_aggregate() -> None:
    sleeper_players = {
        "player-1": {
            "espn_id": 123,
            "first_name": "Runner",
            "last_name": "One",
            "position": "RB",
        }
    }
    projection_data = {
        "players": [
            {
                "player": {
                    "id": 123,
                    "fullName": "Runner One",
                    "defaultPositionId": 2,
                    "stats": [
                        {
                            "seasonId": 2026,
                            "statSourceId": 1,
                            "statSplitTypeId": 0,
                            "scoringPeriodId": 0,
                            "stats": {"23": 250, "24": 1100, "210": 17},
                        }
                    ],
                }
            }
        ]
    }

    mapped = map_projections_to_sleeper(projection_data, sleeper_players, "2026", None)

    assert mapped == {"player-1": {"rush_att": 250, "rush_yd": 1100, "gp": 17}}
