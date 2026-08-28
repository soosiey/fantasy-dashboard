from types import SimpleNamespace

from fantasy_dashboard.player_stats import (
    build_player_identity_image,
    build_player_roster_labels,
    build_player_stat_row,
    build_player_stat_rows,
    build_player_weekly_stat_rows,
    calculate_fantasy_points,
    get_relevant_stat_labels,
    get_rosterable_positions,
    truncate_decimal,
)


def test_decimal_values_are_truncated_without_rounding() -> None:
    assert truncate_decimal(12.999) == 12.99
    assert truncate_decimal(-3.456) == -3.45
    assert truncate_decimal(7) == 7.0


def test_player_identity_image_centers_name_independently_from_owner() -> None:
    identity = build_player_identity_image("Josh Allen", "SleeperUser")

    assert identity.startswith("data:image/svg+xml;utf8,")
    assert "%C2%B7%20SleeperUser" in identity


def test_weekly_player_rows_include_every_week_opponent_and_scoring() -> None:
    rows = build_player_weekly_stat_rows(
        {
            1: {
                "opponent": "BUF",
                "is_away_team": True,
                "stats": {"pass_yd": 250, "pass_td": 2},
            }
        },
        {"pass_yd": 0.04, "pass_td": 4},
    )

    assert len(rows) == 18
    assert rows[0]["Week"] == 1
    assert rows[0]["Opponent"] == "@ BUF"
    assert rows[0]["Fantasy Points"] == 18
    assert rows[0]["Pass Yds"] == 250
    assert rows[1]["Week"] == 2
    assert rows[1]["Opponent"] == "—"


def test_single_week_player_row_uses_selected_stats_and_league_scoring() -> None:
    row = build_player_stat_row(
        {"pass_yd": 251.999, "pass_td": 2},
        {"pass_yd": 0.04, "pass_td": 4},
        7,
    )

    assert row["Week"] == 7
    assert row["Fantasy Points"] == 18.07
    assert row["Pass Yds"] == 251.99
    assert row["Pass TD"] == 2


def test_rostered_players_are_labeled_with_team_and_owner() -> None:
    roster = SimpleNamespace(user_id="user-1", players=["player-1"])
    team = SimpleNamespace(
        user_id="user-1",
        display_team_name="Sunday Stars",
        display_name="SleeperUser",
    )

    assert build_player_roster_labels([roster], [team]) == {
        "player-1": "SleeperUser"
    }


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
    kicker_stats = get_relevant_stat_labels("K")

    assert "Fantasy Points" in quarterback_stats
    assert "Pass Yds" in quarterback_stats
    assert "FG Made" not in quarterback_stats
    assert {
        "FG Made 0–19",
        "FG Made 20–29",
        "FG Made 30–39",
        "FG Made 40–49",
        "FG Made 50–59",
        "FG Made 60+",
    }.issubset(kicker_stats)
