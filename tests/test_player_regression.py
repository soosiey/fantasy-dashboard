from fantasy_dashboard.player_regression import (
    build_regression_observations,
    run_ridge_regression_evaluation,
)


def _historical_inputs():
    players = {
        f"player-{index}": {"position": "QB"}
        for index in range(1, 4)
    }
    actuals = {}
    projections = {}
    for season in (2024, 2025):
        actuals[season] = {}
        projections[season] = {}
        for week in range(1, 19):
            actuals[season][week] = {}
            projections[season][week] = {}
            for index in range(1, 4):
                player_id = f"player-{index}"
                projected_points = 8 + 7 * index + week / 5
                noise = 0.5 if (week + index) % 2 else -0.5
                actual_points = 1.25 * projected_points - 2 + noise
                projections[season][week][player_id] = {"pts": projected_points}
                actuals[season][week][player_id] = {
                    "gp": 1,
                    "pts": actual_points,
                }
    return actuals, projections, players


def test_observation_features_only_use_prior_weeks() -> None:
    actuals = {2024: {1: {"p": {"gp": 1, "pts": 10}}, 2: {"p": {"gp": 1, "pts": 20}}}}
    projections = {2024: {1: {"p": {"pts": 8}}, 2: {"p": {"pts": 15}}}}

    observations = build_regression_observations(
        actuals,
        projections,
        {"p": {"position": "QB"}},
        {"pts": 1},
    )

    assert observations[0].features[1:8] == (0, 0, 0, 0, 0, 0, 0)
    assert observations[1].features[1] == 10
    assert observations[1].features[2] == 10
    assert observations[1].features[4] == 2
    assert observations[1].features[7] == 1


def test_chronological_ridge_evaluation_improves_systematic_residuals() -> None:
    actuals, projections, players = _historical_inputs()
    observations = build_regression_observations(
        actuals,
        projections,
        players,
        {"pts": 1},
    )

    report = run_ridge_regression_evaluation(observations)
    overall = report.evaluations[0]

    assert len(report.predictions) == 54
    assert overall.position == "Overall"
    assert overall.model_mae < overall.provider_mae
    assert overall.mae_improvement > 0.5
    assert len(report.player_summaries) == 3
    assert "QB" in report.final_models
