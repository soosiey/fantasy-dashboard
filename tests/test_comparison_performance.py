import pandas as pd
import pytest

from fantasy_dashboard.components.comparison_data import (
    comparison_positions_are_compatible,
)
from fantasy_dashboard.components.comparison_performance import (
    get_selected_comparison_metrics,
    make_arrow_compatible,
)


@pytest.mark.parametrize(
    ("positions", "expected"),
    [
        (["QB", "QB"], True),
        (["RB", "WR", "TE"], True),
        (["QB", "WR"], False),
        (["DEF", "TE"], False),
    ],
)
def test_comparison_position_compatibility(
    positions: list[str],
    expected: bool,
) -> None:
    assert comparison_positions_are_compatible(positions) is expected


def test_mixed_numeric_and_injury_status_column_is_arrow_compatible() -> None:
    table = make_arrow_compatible(
        pd.DataFrame(
            {
                "Statistic": ["Games played", "Injury status"],
                "Ashton Jeanty (RB)": [12.0, "Questionable"],
                "RB League Average": [10.5, None],
            }
        )
    )

    assert table["Ashton Jeanty (RB)"].tolist() == ["12.00", "Questionable"]
    assert table["RB League Average"].tolist()[0] == 10.5


def test_comparison_metrics_only_include_selected_players_positions() -> None:
    selected_statistics = {
        "rb-player": [{"Key": "touches", "Statistic": "Touches", "Value": 15.0}]
    }
    league_statistics = {
        **selected_statistics,
        "kicker": [
            {
                "Key": "field_goal_rate",
                "Statistic": "Field-goal rate",
                "Value": 90.0,
            }
        ],
    }

    metric_order, _ = get_selected_comparison_metrics(selected_statistics)

    assert metric_order == ["touches"]
    assert "field_goal_rate" not in metric_order
    assert "field_goal_rate" in {
        metric["Key"]
        for statistics in league_statistics.values()
        for metric in statistics
    }
