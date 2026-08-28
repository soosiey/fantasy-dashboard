from fantasy_dashboard.player_trends import build_player_trend_rows


def test_trends_are_resolved_to_player_table_rows() -> None:
    rows = build_player_trend_rows(
        [{"player_id": "player-1", "count": 17}],
        {
            "player-1": {
                "first_name": "Test",
                "last_name": "Player",
                "position": "WR",
                "team": "NYJ",
            }
        },
        "Adds",
    )

    assert rows == [
        {"Player": "Test Player", "Position": "WR", "Team": "NYJ", "Adds": 17}
    ]


def test_unknown_trending_player_uses_safe_fallbacks() -> None:
    rows = build_player_trend_rows(
        [{"player_id": "unknown", "count": 3}], {}, "Drops"
    )

    assert rows == [
        {"Player": "unknown", "Position": "—", "Team": "FA", "Drops": 3}
    ]


def test_trending_rostered_player_includes_roster_label() -> None:
    rows = build_player_trend_rows(
        [{"player_id": "player-1", "count": 4}],
        {"player-1": {"first_name": "Test", "last_name": "Player"}},
        "Adds",
        {"player-1": "SleeperUser"},
    )

    assert rows[0]["Roster"] == "SleeperUser"
