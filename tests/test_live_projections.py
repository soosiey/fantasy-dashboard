from fantasy_dashboard.live_projections import (
    LiveGameContext,
    build_live_projections,
    parse_espn_live_games,
)


def test_parse_espn_live_game_context() -> None:
    payload = {
        "events": [
            {
                "status": {
                    "clock": 450,
                    "period": 3,
                    "type": {"state": "in", "name": "STATUS_IN_PROGRESS"},
                },
                "competitions": [
                    {
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "10",
                                "team": {"id": "1", "abbreviation": "SEA"},
                            },
                            {
                                "homeAway": "away",
                                "score": "14",
                                "team": {"id": "2", "abbreviation": "NE"},
                            },
                        ],
                        "situation": {"possession": "1"},
                    }
                ],
            }
        ]
    }

    assert parse_espn_live_games(payload) == [
        LiveGameContext("SEA", "NE", 10, 14, 0.625, "SEA")
    ]


def test_live_projection_blends_usage_and_keeps_actual_points() -> None:
    baseline = {
        "qb": {"pass_att": 40, "pass_cmp": 26, "pass_yd": 280, "pass_td": 2},
        "wr1": {"rec_tgt": 10, "rec": 7, "rec_yd": 100, "rec_td": 0.5},
        "wr2": {"rec_tgt": 10, "rec": 6, "rec_yd": 80, "rec_td": 0.4},
        "rb": {"rush_att": 20, "rush_yd": 90, "rush_td": 0.6},
    }
    actual = {
        "qb": {"pass_att": 20, "pass_cmp": 13, "pass_yd": 140, "pass_td": 1},
        "wr1": {"rec_tgt": 8, "rec": 6, "rec_yd": 70, "rec_td": 1},
        "wr2": {"rec_tgt": 2, "rec": 1, "rec_yd": 8},
        "rb": {"rush_att": 10, "rush_yd": 45},
    }
    players = {player_id: {"team": "SEA", "active": True} for player_id in baseline}
    result = build_live_projections(
        baseline,
        actual,
        players,
        [LiveGameContext("SEA", "NE", 7, 14, 0.5)],
    )

    assert result["wr1"]["rec_tgt"] > result["wr2"]["rec_tgt"]
    assert result["wr1"]["rec_td"] >= 1
    assert result["qb"]["pass_yd"] > 140
    assert result["rb"]["rush_yd"] > 45


def test_unavailable_player_gets_no_remaining_projection() -> None:
    result = build_live_projections(
        {"player": {"rec_tgt": 8, "rec": 5, "rec_yd": 70}},
        {"player": {"rec_tgt": 1, "rec": 1, "rec_yd": 9}},
        {"player": {"team": "SEA", "injury_status": "Out"}},
        [LiveGameContext("SEA", "NE", 0, 0, 0.5)],
    )

    assert result["player"] == {"rec_tgt": 1, "rec": 1, "rec_yd": 9}
