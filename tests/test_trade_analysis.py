from fantasy_dashboard.models.league import LeagueModel
from fantasy_dashboard.trade_analysis import grade_hypothetical_trade


def _league() -> LeagueModel:
    return LeagueModel.from_api(
        {
            "league_id": "league-1",
            "total_rosters": 4,
            "status": "in_season",
            "sport": "nfl",
            "settings": {
                "waiver_budget": 100,
                "playoff_teams": 2,
                "num_teams": 4,
                "playoff_week_start": 15,
                "waiver_day_of_week": 2,
                "trade_deadline": 11,
                "reserve_slots": 0,
            },
            "roster_positions": ["QB", "RB", "WR", "BN"],
            "name": "Test League",
            "draft_id": "draft-1",
            "scoring_settings": {"pts": 1},
            "bracket_id": "",
            "loser_bracket_id": "",
            "avatar": "",
            "season": "2026",
        }
    )


def _player(position: str) -> dict:
    return {"position": position, "fantasy_positions": [position]}


def test_equal_same_position_trade_is_neutral_for_both_users() -> None:
    players = {
        "first-rb": _player("RB"),
        "second-rb": _player("RB"),
        **{f"replacement-{index}": _player("RB") for index in range(4)},
    }
    projections = {
        "first-rb": {"pts": 20},
        "second-rb": {"pts": 20},
        **{f"replacement-{index}": {"pts": 5} for index in range(4)},
    }

    grade = grade_hypothetical_trade(
        _league(),
        ["first-rb"],
        ["second-rb"],
        ["first-rb"],
        ["second-rb"],
        players,
        projections,
    )

    assert grade.first.score == 75
    assert grade.second.score == 75
    assert grade.first.letter == "C"
    assert grade.second.letter == "C"


def test_stronger_received_package_rewards_one_side_and_penalizes_the_other() -> None:
    players = {
        "weak-rb": _player("RB"),
        "strong-rb": _player("RB"),
        **{f"replacement-{index}": _player("RB") for index in range(4)},
    }
    projections = {
        "weak-rb": {"pts": 20},
        "strong-rb": {"pts": 35},
        **{f"replacement-{index}": {"pts": 5} for index in range(4)},
    }

    grade = grade_hypothetical_trade(
        _league(),
        ["weak-rb"],
        ["strong-rb"],
        ["weak-rb"],
        ["strong-rb"],
        players,
        projections,
    )

    assert grade.first.strength_score > 75
    assert grade.second.strength_score < 75
    assert grade.first.score > grade.second.score


def test_both_users_can_improve_by_trading_redundant_depth_for_a_need() -> None:
    players = {
        "first-qb": _player("QB"),
        "first-rb": _player("RB"),
        "first-wr": _player("WR"),
        "first-extra-wr": _player("WR"),
        "second-qb": _player("QB"),
        "second-rb": _player("RB"),
        "second-wr": _player("WR"),
        "second-extra-rb": _player("RB"),
    }
    projections = {
        "first-qb": {"pts": 30},
        "first-rb": {"pts": 5},
        "first-wr": {"pts": 40},
        "first-extra-wr": {"pts": 30},
        "second-qb": {"pts": 30},
        "second-rb": {"pts": 40},
        "second-wr": {"pts": 5},
        "second-extra-rb": {"pts": 30},
    }
    for position in ("QB", "RB", "WR"):
        for index in range(4):
            player_id = f"{position.lower()}-replacement-{index}"
            players[player_id] = _player(position)
            projections[player_id] = {"pts": 5}

    grade = grade_hypothetical_trade(
        _league(),
        ["first-qb", "first-rb", "first-wr", "first-extra-wr"],
        ["second-qb", "second-rb", "second-wr", "second-extra-rb"],
        ["first-extra-wr"],
        ["second-extra-rb"],
        players,
        projections,
    )

    assert grade.first.strength_score == 75
    assert grade.second.strength_score == 75
    assert grade.first.roster_fit_score > 75
    assert grade.second.roster_fit_score > 75
    assert grade.first.roster_utility_change > 0
    assert grade.second.roster_utility_change > 0
