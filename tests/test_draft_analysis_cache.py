from fantasy_dashboard import draft_analysis_cache
from fantasy_dashboard.draft_grading import (
    DraftGradeWeights,
    DraftPickAlternative,
    DraftPickGrade,
)
from fantasy_dashboard.league_predictions import DraftTeamProjection


def _pick_grade(score: float) -> DraftPickGrade:
    return DraftPickGrade(
        score=score,
        letter="A",
        strength_score=95.0,
        roster_fit_score=90.0,
        projected_points=300.0,
        position_average=200.0,
        marginal_roster_value=50.0,
        best_available_roster_value=55.0,
        wait_cost=4.0,
        cost_score=None,
        fair_value=None,
        amount_paid=None,
        alternatives=(DraftPickAlternative("player-2", 96.0),),
    )


def _team_projection(probability: float) -> DraftTeamProjection:
    return DraftTeamProjection(
        user_id="user-1",
        weekly_mean=120.0,
        weekly_standard_deviation=15.0,
        average_weekly_win_probability=0.6,
        playoff_probability=0.7,
        championship_probability=probability,
        championship_grade_score=90.0,
    )


def test_completed_pick_grades_are_calculated_only_when_cache_is_missing(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        draft_analysis_cache,
        "DRAFT_ANALYSIS_CACHE_DIR",
        tmp_path,
    )
    weights = DraftGradeWeights()
    calculations = 0

    def calculate() -> dict[int, DraftPickGrade]:
        nonlocal calculations
        calculations += 1
        return {1: _pick_grade(92.0)}

    first = draft_analysis_cache.load_or_create_draft_pick_grades(
        "draft-1", weights, calculate
    )
    second = draft_analysis_cache.load_or_create_draft_pick_grades(
        "draft-1", weights, calculate
    )

    assert calculations == 1
    assert first == second
    assert second[1].alternatives == (DraftPickAlternative("player-2", 96.0),)


def test_different_grade_weights_have_independent_persistent_results(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(draft_analysis_cache, "DRAFT_ANALYSIS_CACHE_DIR", tmp_path)
    calculations = 0

    def calculate() -> dict[int, DraftPickGrade]:
        nonlocal calculations
        calculations += 1
        return {1: _pick_grade(float(calculations))}

    default = draft_analysis_cache.load_or_create_draft_pick_grades(
        "draft-1", DraftGradeWeights(), calculate
    )
    changed = draft_analysis_cache.load_or_create_draft_pick_grades(
        "draft-1", DraftGradeWeights(bench_depth=0.5), calculate
    )

    assert calculations == 2
    assert default[1].score != changed[1].score


def test_draft_simulation_is_calculated_only_when_cache_is_missing(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(draft_analysis_cache, "DRAFT_ANALYSIS_CACHE_DIR", tmp_path)
    calculations = 0

    def calculate() -> dict[str, DraftTeamProjection]:
        nonlocal calculations
        calculations += 1
        return {"user-1": _team_projection(0.25)}

    first = draft_analysis_cache.load_or_create_draft_team_projections(
        "draft-1", calculate
    )
    second = draft_analysis_cache.load_or_create_draft_team_projections(
        "draft-1", calculate
    )

    assert calculations == 1
    assert first == second
