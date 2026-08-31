import pandas as pd
import pytest

from fantasy_dashboard.components.comparison_performance import (
    comparison_positions_are_compatible,
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
