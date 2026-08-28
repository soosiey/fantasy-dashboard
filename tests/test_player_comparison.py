from fantasy_dashboard.components.player_comparison import (
    _render_comparison_table,
)
from fantasy_dashboard.player_stats import get_relevant_stat_fields


# Better values, including fewer interceptions, should receive the subtle winner class.
def test_comparison_table_marks_better_stat_cells() -> None:
    fields = get_relevant_stat_fields("QB")
    table = _render_comparison_table(
        "left-player",
        {
            "first_name": "Left",
            "last_name": "Quarterback",
            "team": "BUF",
            "fantasy_positions": ["QB"],
        },
        {"pass_yd": 300, "pass_int": 1},
        "right-player",
        {
            "first_name": "Right",
            "last_name": "Quarterback",
            "team": "NYJ",
            "fantasy_positions": ["QB"],
        },
        {"pass_yd": 200, "pass_int": 2},
        {"pass_yd": 0.04, "pass_int": -2},
        fields,
    )

    assert "Left Quarterback" in table
    assert "Right Quarterback" in table
    assert (
        '<td class="comparison-stat-value comparison-stat-left comparison-stat-winner">'
        "300.00</td>"
        '<td class="comparison-stat-label">Pass Yds</td>'
        '<td class="comparison-stat-value comparison-stat-right">200.00</td>'
    ) in table
    assert (
        '<td class="comparison-stat-value comparison-stat-left comparison-stat-winner">'
        "1.00</td>"
        '<td class="comparison-stat-label">Pass INT</td>'
        '<td class="comparison-stat-value comparison-stat-right">2.00</td>'
    ) in table


# Mixed-position comparisons should show the union of each player's relevant stats.
def test_relevant_comparison_fields_union_both_positions() -> None:
    labels = {label for label, _ in get_relevant_stat_fields("RB", "WR")}

    assert {"Fantasy Points", "Games", "Carries", "Targets", "Rec Yds"} <= labels
    assert "FG Made" not in labels


def test_kicker_comparison_includes_every_made_field_goal_distance() -> None:
    labels = {label for label, _ in get_relevant_stat_fields("K")}

    assert {
        "FG Made 0–19",
        "FG Made 20–29",
        "FG Made 30–39",
        "FG Made 40–49",
        "FG Made 50–59",
        "FG Made 60+",
    }.issubset(labels)
