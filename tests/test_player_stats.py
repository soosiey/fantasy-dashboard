from types import SimpleNamespace

from fantasy_dashboard.player_stats import (
    build_player_stat_rows,
    calculate_fantasy_points,
    get_relevant_stat_labels,
    get_rosterable_positions,
)


# Flex slots should expose only their concrete, filterable player positions.
def test_rosterable_positions_expand_flex_slots() -> None:
    positions = get_rosterable_positions(
        ["QB", "RB", "WR", "TE", "REC_FLEX", "SUPER_FLEX", "BN", "IR"]
    )

    assert positions == ["QB", "RB", "WR", "TE"]


# Availability must use current league rosters and missing stats must remain zero.
def test_available_players_exclude_currently_rostered_players() -> None:
    players = {
        "rostered": {
            "active": True,
            "fantasy_positions": ["QB"],
            "first_name": "Rostered",
            "last_name": "Player",
            "position": "QB",
            "team": "BUF",
        },
        "available": {
            "active": True,
            "fantasy_positions": ["QB"],
            "first_name": "Available",
            "last_name": "Player",
            "position": "QB",
            "team": "NYJ",
        },
    }
    rosters = [SimpleNamespace(players=["rostered"])]

    rows = build_player_stat_rows(
        players,
        rosters,
        {},
        {"pass_yd": 0.04},
        ["QB"],
        selected_position="QB",
        available_only=True,
    )

    assert len(rows) == 1
    assert rows[0]["Player"] == "Available Player"
    assert rows[0]["Availability"] == "Available"
    assert rows[0]["Fantasy Points"] == 0
    assert rows[0]["Pass Yds"] == 0
    assert rows[0]["Rush Yds"] == 0
    assert rows[0]["FG Made"] == 0


# League scoring remains ready for real aggregate data when it is connected later.
def test_fantasy_points_use_league_scoring_settings() -> None:
    points = calculate_fantasy_points(
        {"pass_yd": 250, "pass_td": 2, "pass_int": 1},
        {"pass_yd": 0.04, "pass_td": 4, "pass_int": -2},
    )

    assert points == 16


# Highlight metadata should distinguish relevant columns without hiding others.
def test_relevant_stats_are_position_specific() -> None:
    quarterback_stats = get_relevant_stat_labels("QB")

    assert "Fantasy Points" in quarterback_stats
    assert "Pass Yds" in quarterback_stats
    assert "FG Made" not in quarterback_stats
