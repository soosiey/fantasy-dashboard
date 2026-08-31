import pytest

from fantasy_dashboard.player_performance import (
    build_consistency_statistics,
    build_consistency_trend,
    build_core_performance_statistics,
    build_core_performance_trend,
    build_metric_average_values,
    build_position_average_statistics,
    build_projection_accuracy_statistics,
    build_projection_accuracy_trend,
    is_eligible_game,
)


def test_core_performance_statistics_include_zeroes_and_reference_metrics() -> None:
    statistics = build_core_performance_statistics(
        [
            {"Week": 1, "Opponent": "NYJ", "Fantasy Points": 0},
            {"Week": 2, "Opponent": "MIA", "Fantasy Points": 10},
            {"Week": 3, "Opponent": "KC", "Fantasy Points": 20},
            {"Week": 4, "Opponent": "NE", "Fantasy Points": 30},
        ],
        "Fantasy Points",
    )
    values_by_statistic = {row["Statistic"]: row["Value"] for row in statistics}

    assert values_by_statistic["Average"] == 15
    assert values_by_statistic["Median"] == 15
    assert values_by_statistic["Standard deviation"] == pytest.approx(11.1803398875)
    assert values_by_statistic["Floor (25th percentile)"] == 7.5
    assert values_by_statistic["Ceiling (75th percentile)"] == 22.5
    assert values_by_statistic["Ceiling (90th percentile)"] == 27
    assert values_by_statistic["Season total"] == 60
    assert values_by_statistic["Games played"] == 4
    assert values_by_statistic["Last-3-game average"] == 20
    assert values_by_statistic["Recent difference from season average"] == 5
    assert values_by_statistic["Recent percent change"] == pytest.approx(100 / 3)
    assert (
        next(row["Context"] for row in statistics if row["Statistic"] == "Best week")
        == "Week 4 · vs NE"
    )
    assert (
        next(row["Context"] for row in statistics if row["Statistic"] == "Worst week")
        == "Week 1 · vs NYJ"
    )


def test_core_performance_statistics_omit_percent_change_for_zero_average() -> None:
    statistics = build_core_performance_statistics(
        [{"Week": 1, "Opponent": "NYJ", "Fantasy Points": 0}],
        "Fantasy Points",
    )

    assert (
        next(
            row["Value"]
            for row in statistics
            if row["Statistic"] == "Recent percent change"
        )
        is None
    )


def test_eligible_game_excludes_explicit_dnp_but_keeps_a_played_zero() -> None:
    assert not is_eligible_game({"stats": {"gp": 0, "pass_yd": 0}})
    assert is_eligible_game({"stats": {"gp": 1, "pass_yd": 0}})
    assert is_eligible_game({"stats": {"pass_yd": 0}})
    assert not is_eligible_game({"stats": {}})


def test_core_performance_trend_recalculates_metric_through_each_week() -> None:
    trend = build_core_performance_trend(
        [
            {"Week": 1, "Opponent": "NYJ", "Fantasy Points": 10},
            {"Week": 2, "Opponent": "MIA", "Fantasy Points": 20},
            {"Week": 3, "Opponent": "KC", "Fantasy Points": 0},
        ],
        "Fantasy Points",
        "average",
    )

    assert [row["Value"] for row in trend] == [10, 15, 10]
    assert [row["Week Label"] for row in trend] == [
        "Week 1 · vs NYJ",
        "Week 2 · vs MIA",
        "Week 3 · vs KC",
    ]


def test_position_average_statistics_average_each_players_metric() -> None:
    averages = build_position_average_statistics(
        {
            "player-1": [
                {"Week": 1, "Fantasy Points": 10},
                {"Week": 2, "Fantasy Points": 20},
            ],
            "player-2": [
                {"Week": 1, "Fantasy Points": 20},
                {"Week": 2, "Fantasy Points": 40},
            ],
            "no-games": [],
        },
        "Fantasy Points",
    )

    assert averages["average"] == 22.5
    assert averages["season_total"] == 45
    assert averages["games_played"] == 2


def test_projection_accuracy_uses_only_matched_completed_games() -> None:
    statistics = build_projection_accuracy_statistics(
        [
            {"Week": 1, "Fantasy Points": 10},
            {"Week": 2, "Fantasy Points": 20},
            {"Week": 3, "Fantasy Points": 0},
        ],
        [
            {"Week": 1, "Fantasy Points": 12},
            {"Week": 2, "Fantasy Points": 16},
            {"Week": 4, "Fantasy Points": 30},
        ],
        "Fantasy Points",
        hit_tolerance=3,
    )
    values = {row["Statistic"]: row["Value"] for row in statistics}

    assert values["Actual average"] == 15
    assert values["Predicted average"] == 14
    assert values["MAE"] == 3
    assert values["Bias"] == 1
    assert values["RMSE"] == pytest.approx(3.1622776602)
    assert values["Hit rate"] == 50
    assert values["r"] == pytest.approx(1)


def test_projection_correlation_is_unavailable_for_insufficient_variance() -> None:
    statistics = build_projection_accuracy_statistics(
        [{"Week": 1, "Fantasy Points": 10}],
        [{"Week": 1, "Fantasy Points": 12}],
        "Fantasy Points",
    )

    assert next(row["Value"] for row in statistics if row["Statistic"] == "r") is None


def test_consistency_statistics_follow_reference_thresholds_and_trend() -> None:
    statistics = build_consistency_statistics(
        [
            {"Week": 1, "Fantasy Points": 10},
            {"Week": 2, "Fantasy Points": 20},
            {"Week": 3, "Fantasy Points": 30},
        ],
        [
            {"Week": 1, "Fantasy Points": 5},
            {"Week": 2, "Fantasy Points": 20},
            {"Week": 3, "Fantasy Points": 35},
        ],
        "Fantasy Points",
        consistency_band_percent=20,
        boom_bust_tolerance=3,
    )
    values = {row["Statistic"]: row["Value"] for row in statistics}

    assert values["Consistency rate"] == pytest.approx(100 / 3)
    assert values["Boom rate"] == pytest.approx(100 / 3)
    assert values["Bust rate"] == pytest.approx(100 / 3)
    assert values["Rolling 3-game average"] == 20
    assert values["Trend slope"] == pytest.approx(10)


def test_metric_average_values_ignore_unavailable_peer_metrics() -> None:
    averages = build_metric_average_values(
        {
            "player-1": [
                {"Key": "mae", "Value": 2.0},
                {"Key": "correlation", "Value": None},
            ],
            "player-2": [
                {"Key": "mae", "Value": 4.0},
                {"Key": "correlation", "Value": 0.5},
            ],
        }
    )

    assert averages == {"mae": 3.0, "correlation": 0.5}


def test_projection_and_consistency_trends_recalculate_through_each_week() -> None:
    actual_rows = [
        {"Week": 1, "Fantasy Points": 10},
        {"Week": 2, "Fantasy Points": 20},
        {"Week": 3, "Fantasy Points": 30},
    ]
    predicted_rows = [
        {"Week": 1, "Fantasy Points": 8},
        {"Week": 2, "Fantasy Points": 16},
        {"Week": 3, "Fantasy Points": 24},
    ]

    accuracy_trend = build_projection_accuracy_trend(
        actual_rows,
        predicted_rows,
        "Fantasy Points",
        "mae",
    )
    consistency_trend = build_consistency_trend(
        actual_rows,
        predicted_rows,
        "Fantasy Points",
        "rolling_average_3",
    )

    assert [row["Value"] for row in accuracy_trend] == [2, 3, 4]
    assert [row["Value"] for row in consistency_trend] == [None, None, 20]
