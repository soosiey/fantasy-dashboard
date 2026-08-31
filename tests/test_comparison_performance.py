import pandas as pd
import pytest

from fantasy_dashboard.components.comparison_data import (
    comparison_positions_are_compatible,
)
from fantasy_dashboard.components.comparison_performance import (
    get_metric_winner_player_id,
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


@pytest.mark.parametrize(
    ("metric_key", "values", "expected"),
    [
        ("average", {"player-1": 18.0, "player-2": 21.0}, "player-2"),
        ("mae", {"player-1": 2.5, "player-2": 4.0}, "player-1"),
        ("interception_rate", {"player-1": 1.8, "player-2": 2.4}, "player-1"),
        ("bias", {"player-1": -0.5, "player-2": 1.0}, "player-1"),
    ],
)
def test_metric_winner_respects_metric_direction(
    metric_key: str,
    values: dict[str, float],
    expected: str,
) -> None:
    assert get_metric_winner_player_id(metric_key, values) == expected


def test_metric_winner_does_not_choose_a_tied_or_only_available_player() -> None:
    assert get_metric_winner_player_id(
        "average",
        {"player-1": 20.0, "player-2": 20.0},
    ) is None
    assert get_metric_winner_player_id(
        "average",
        {"player-1": 20.0, "player-2": None},
    ) is None
