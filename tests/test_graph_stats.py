from fantasy_dashboard.graph_stats import (
    build_actual_weekly_stat_rows,
    build_week_axis_labels,
)


def test_actual_graph_rows_keep_recorded_zeroes_and_omit_missing_weeks() -> None:
    rows = build_actual_weekly_stat_rows(
        {
            1: {"stats": {"pass_yd": 0}},
            3: {"stats": {"pass_yd": 250}},
        },
        {"pass_yd": 0.04},
    )

    assert [row["Week"] for row in rows] == [1, 3]
    assert [row["Fantasy Points"] for row in rows] == [0, 10]


def test_week_axis_labels_include_scheduled_opponents_and_actual_fallbacks() -> None:
    labels = build_week_axis_labels(
        [
            {"week": 1, "home": "BUF", "away": "NYJ"},
            {"week": 2, "home": "KC", "away": "BUF"},
        ],
        "BUF",
        {3: {"opponent": "MIA"}},
    )

    assert labels == {
        1: "Week 1 · vs NYJ",
        2: "Week 2 · vs KC",
        3: "Week 3 · vs MIA",
    }
