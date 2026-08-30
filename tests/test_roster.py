from types import SimpleNamespace

from fantasy_dashboard.roster import get_roster_player_order


def test_roster_player_order_places_starters_before_bench_and_reserve() -> None:
    roster = SimpleNamespace(
        starters=["starter-2", "starter-1", "0"],
        players=["bench-2", "starter-1", "reserve-1", "bench-1", "starter-2"],
        reserve=["reserve-1"],
    )

    assert get_roster_player_order(roster) == [
        "starter-2",
        "starter-1",
        "bench-2",
        "bench-1",
        "reserve-1",
    ]
