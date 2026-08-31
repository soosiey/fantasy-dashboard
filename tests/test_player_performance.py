import pytest

from fantasy_dashboard.player_performance import (
    build_availability_statistics,
    build_availability_trend,
    build_consistency_statistics,
    build_consistency_trend,
    build_core_performance_statistics,
    build_core_performance_trend,
    build_efficiency_statistics,
    build_efficiency_trend,
    build_metric_average_values,
    build_opportunity_statistics,
    build_opportunity_trend,
    build_position_average_statistics,
    build_projection_accuracy_statistics,
    build_projection_accuracy_trend,
    get_team_completed_weeks,
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


def test_opportunity_and_efficiency_use_cached_volume_with_context() -> None:
    weekly_rows = [
        {
            "Week": 1,
            "Fantasy Points": 12,
            "_Raw Stats": {
                "rush_att": 10,
                "rush_yd": 50,
                "rush_td": 1,
                "rec": 4,
                "rec_tgt": 5,
                "rec_yd": 30,
                "rec_td": 0,
                "off_snp": 30,
                "tm_off_snp": 60,
                "rush_rz_att": 2,
                "rec_rz_tgt": 1,
            },
        },
        {
            "Week": 2,
            "Fantasy Points": 18,
            "_Raw Stats": {
                "rush_att": 15,
                "rush_yd": 100,
                "rush_td": 0,
                "rec": 5,
                "rec_tgt": 10,
                "rec_yd": 60,
                "rec_td": 1,
                "off_snp": 45,
                "tm_off_snp": 60,
                "rush_rz_att": 3,
                "rec_rz_tgt": 2,
            },
        },
    ]
    opportunity = {
        row["Statistic"]: row for row in build_opportunity_statistics(weekly_rows, "RB")
    }
    efficiency = {
        row["Statistic"]: row for row in build_efficiency_statistics(weekly_rows, "RB")
    }

    assert opportunity["Touches"]["Value"] == 34
    assert opportunity["Targets"]["Value"] == 15
    assert opportunity["Snap share"]["Value"] == 62.5
    assert opportunity["Red-zone opportunities"]["Value"] == 8
    assert efficiency["Fantasy points per touch"]["Value"] == pytest.approx(30 / 34)
    assert efficiency["Yards per carry"]["Value"] == 6
    assert efficiency["Catch rate"]["Value"] == 60
    assert efficiency["Yards per target"]["Value"] == 6


def test_availability_excludes_byes_and_retains_injury_context() -> None:
    schedule = [
        {"week": 1, "home": "BUF", "away": "NYJ", "status": "complete"},
        {"week": 2, "home": "MIA", "away": "NYJ", "status": "complete"},
        {"week": 3, "home": "BUF", "away": "MIA", "status": "scheduled"},
    ]
    assert get_team_completed_weeks(schedule, "BUF") == [1]
    assert get_team_completed_weeks(schedule, "NYJ") == [1, 2]

    statistics = build_availability_statistics(
        [{"Week": 1, "Fantasy Points": 0}],
        2,
        "Questionable",
    )
    values = {row["Statistic"]: row["Value"] for row in statistics}

    assert values["Games played"] == 1
    assert values["Games missed"] == 1
    assert values["Availability rate"] == 50
    assert (
        next(
            row["Context"] for row in statistics if row["Statistic"] == "Injury status"
        )
        == "Current Sleeper designation: Questionable"
    )


def test_new_performance_metric_trends_recalculate_cumulatively() -> None:
    weekly_rows = [
        {
            "Week": 1,
            "Fantasy Points": 10,
            "_Raw Stats": {"rush_att": 10, "rush_yd": 50, "rec": 2},
        },
        {
            "Week": 2,
            "Fantasy Points": 20,
            "_Raw Stats": {"rush_att": 20, "rush_yd": 120, "rec": 2},
        },
    ]

    assert [
        row["Value"] for row in build_opportunity_trend(weekly_rows, "RB", "touches")
    ] == [12, 34]
    assert [
        row["Value"]
        for row in build_efficiency_trend(weekly_rows, "RB", "yards_per_carry")
    ] == [5, pytest.approx(170 / 30)]
    assert [
        row["Value"]
        for row in build_availability_trend(
            weekly_rows,
            [1, 2, 3],
            None,
            "availability_rate",
        )
    ] == [100, 100, pytest.approx(200 / 3)]
