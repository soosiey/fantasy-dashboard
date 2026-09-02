from fantasy_dashboard.draft_grading import (
    DraftGradeWeights,
    grade_draft_picks,
    letter_grade,
)
from fantasy_dashboard.models.draft import DraftPickModel
from fantasy_dashboard.models.league import LeagueModel


def _league() -> LeagueModel:
    return LeagueModel.from_api(
        {
            "league_id": "league-1",
            "total_rosters": 3,
            "status": "in_season",
            "sport": "nfl",
            "settings": {
                "waiver_budget": 100,
                "playoff_teams": 2,
                "num_teams": 3,
                "playoff_week_start": 15,
                "waiver_day_of_week": 2,
                "trade_deadline": 11,
                "reserve_slots": 0,
            },
            "roster_positions": ["RB", "K", "BN"],
            "name": "Grade League",
            "draft_id": "draft-1",
            "scoring_settings": {"pts": 1},
            "bracket_id": "winners-1",
            "loser_bracket_id": "losers-1",
            "avatar": "",
            "season": "2026",
            "season_type": "regular",
        }
    )


def _players() -> dict[str, dict[str, object]]:
    positions = {
        "rb-1": "RB",
        "rb-2": "RB",
        "rb-3": "RB",
        "rb-4": "RB",
        "k-1": "K",
        "k-2": "K",
        "k-3": "K",
        "k-4": "K",
    }
    return {
        player_id: {
            "player_id": player_id,
            "position": position,
            "fantasy_positions": [position],
        }
        for player_id, position in positions.items()
    }


def _projections() -> dict[str, dict[str, float]]:
    return {
        "rb-1": {"pts": 120},
        "rb-2": {"pts": 115},
        "rb-3": {"pts": 80},
        "rb-4": {"pts": 70},
        "k-1": {"pts": 55},
        "k-2": {"pts": 54},
        "k-3": {"pts": 53},
        "k-4": {"pts": 52},
    }


def test_letter_grade_uses_standard_thresholds() -> None:
    assert [letter_grade(score) for score in (90, 80, 70, 60, 59.9)] == [
        "A",
        "B",
        "C",
        "D",
        "F",
    ]


def test_score_weights_can_isolate_positional_strength() -> None:
    grades = grade_draft_picks(
        _league(),
        [DraftPickModel(1, "rb-2", "RB Two", None, "user-1", 1)],
        _players(),
        _projections(),
        DraftGradeWeights(strength=1, roster_fit=0, wait_cost=0),
    )

    assert grades[1].score == grades[1].strength_score
    assert grades[1].position_average > 0
    assert grades[1].projected_points == 115


def test_bench_depth_can_outweigh_a_shallow_unfilled_position() -> None:
    picks = [
        DraftPickModel(1, "rb-1", "RB One", None, "user-1", 1),
        DraftPickModel(2, "rb-2", "RB Two", None, "user-1", 2),
        DraftPickModel(3, "k-1", "K One", None, "user-1", 3),
    ]
    without_depth = grade_draft_picks(
        _league(),
        picks,
        _players(),
        _projections(),
        DraftGradeWeights(strength=0, roster_fit=1, bench_depth=0, wait_cost=0),
    )
    with_depth = grade_draft_picks(
        _league(),
        picks,
        _players(),
        _projections(),
        DraftGradeWeights(strength=0, roster_fit=1, bench_depth=1, wait_cost=0),
    )

    assert with_depth[2].roster_fit_score > without_depth[2].roster_fit_score


def test_last_pick_enforces_remaining_required_starting_slot() -> None:
    grades = grade_draft_picks(
        _league(),
        [
            DraftPickModel(1, "rb-1", "RB One", None, "user-1", 1),
            DraftPickModel(2, "rb-2", "RB Two", None, "user-1", 2),
        ],
        _players(),
        _projections(),
        DraftGradeWeights(strength=0, roster_fit=1, bench_depth=1, wait_cost=0),
    )

    assert grades[2].roster_fit_score == 0


def test_auction_pick_uses_fair_value_at_that_point_in_the_draft() -> None:
    picks = [
        DraftPickModel(1, "rb-1", "RB One", 80, "user-1", 1),
        DraftPickModel(2, "rb-2", "RB Two", 20, "user-2", 1),
        DraftPickModel(3, "k-1", "K One", 1, "user-3", 1),
    ]

    grades = grade_draft_picks(
        _league(),
        picks,
        _players(),
        _projections(),
        DraftGradeWeights(strength=0, roster_fit=0, cost=1, wait_cost=0),
    )

    assert grades[1].fair_value is not None
    assert grades[2].fair_value is not None
    assert grades[1].fair_value > grades[2].fair_value
    assert grades[1].cost_score is not None
    assert grades[1].cost_score < 100
    assert grades[1].score == grades[1].cost_score


def test_snake_pick_does_not_include_auction_cost_weight() -> None:
    grades = grade_draft_picks(
        _league(),
        [DraftPickModel(1, "rb-2", "RB Two", None, "user-1", 1)],
        _players(),
        _projections(),
        DraftGradeWeights(strength=1, roster_fit=0, cost=100, wait_cost=0),
    )

    assert grades[1].cost_score is None
    assert grades[1].fair_value is None
    assert grades[1].score == grades[1].strength_score


def test_snake_pick_lists_up_to_three_higher_scoring_available_options() -> None:
    grades = grade_draft_picks(
        _league(),
        [
            DraftPickModel(1, "rb-4", "RB Four", None, "user-1", 1),
            DraftPickModel(2, "k-1", "K One", None, "user-1", 2),
        ],
        _players(),
        _projections(),
        DraftGradeWeights(strength=1, roster_fit=0, wait_cost=0),
    )

    alternatives = grades[1].alternatives
    assert alternatives is not None
    assert [option.player_id for option in alternatives] == ["rb-1", "k-1", "rb-2"]
    assert all(option.score > grades[1].score for option in alternatives)


def test_auction_pick_does_not_include_snake_alternatives() -> None:
    grades = grade_draft_picks(
        _league(),
        [DraftPickModel(1, "rb-4", "RB Four", 1, "user-1", 1)],
        _players(),
        _projections(),
        DraftGradeWeights(),
    )

    assert grades[1].alternatives is None
