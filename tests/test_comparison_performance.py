import pytest

from fantasy_dashboard.components.comparison_performance import (
    comparison_positions_are_compatible,
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
