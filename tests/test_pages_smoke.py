from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fantasy_dashboard.components.comparison_selection import COMPARISON_COLUMN
from fantasy_dashboard.models.matchup import WeeklyMatchupContainer

pytestmark = pytest.mark.smoke
APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _query_value(app: AppTest, key: str) -> str:
    value = app.query_params[key]
    return str(value[-1] if isinstance(value, list) else value)


def _authenticated_app(fake_page_backend) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.session_state["sleeper_user"] = fake_page_backend
    app.session_state["league_id"] = "league-1"
    app.session_state["user_id"] = "user-1"
    app.query_params["league_id"] = "league-1"
    return app.run()


def _assert_page(app: AppTest, expected_title: str) -> None:
    assert not app.exception
    assert expected_title in [title.value for title in app.title]


def test_login_page_renders_without_provider_requests(fake_page_backend) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()

    _assert_page(app, "Fantasy Football Dashboard")


def test_leagues_page_renders_for_authenticated_user(fake_page_backend) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.session_state["sleeper_user"] = fake_page_backend
    app.run()

    _assert_page(app, "Leagues")
    assert app.selectbox[0].label == "Season"


def test_authenticated_root_opens_selected_league_overview(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)

    _assert_page(app, "Overview")
    assert any(button.label == "Refresh Current Week" for button in app.button)


def test_global_current_week_refresh_is_forced_from_bottom_bar(
    monkeypatch,
    fake_page_backend,
) -> None:
    from fantasy_dashboard import data

    refresh_calls: list[bool] = []

    def refresh_current_week_input_data(*, force: bool = False):
        refresh_calls.append(force)
        return "2026", "regular", 1

    monkeypatch.setattr(
        data,
        "refresh_current_week_input_data",
        refresh_current_week_input_data,
    )
    app = _authenticated_app(fake_page_backend)

    app.button(key="refresh-current-week-input-data").click().run()

    _assert_page(app, "Overview")
    assert True in refresh_calls
    assert app.button(key="refresh-current-week-input-data").disabled


def test_cold_deep_link_redirects_to_login(fake_page_backend) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    app.switch_page("pages/matchups.py")
    app.query_params["league_id"] = "league-1"
    app.query_params["week"] = "4"
    app.query_params["stats"] = "predicted"
    app.run()

    _assert_page(app, "Fantasy Football Dashboard")
    assert app.session_state["_pending_route"] == "matchups"
    pending_query = app.session_state["_pending_query_params"]
    assert str(pending_query["league_id"]) == "league-1"
    assert str(pending_query["week"]) == "4"
    assert str(pending_query["stats"]) == "predicted"


def test_authenticated_matchup_deep_link_restores_view(fake_page_backend) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.session_state["sleeper_user"] = fake_page_backend
    app.run()
    app.switch_page("pages/matchups.py")
    app.query_params["league_id"] = "league-1"
    app.query_params["week"] = "4"
    app.query_params["stats"] = "predicted"
    app.run()

    _assert_page(app, "Matchups")
    assert _query_value(app, "league_id") == "league-1"
    assert _query_value(app, "week") == "4"
    assert _query_value(app, "stats") == "predicted"


@pytest.mark.parametrize(
    ("legacy_page", "expected_title"),
    [
        ("pages/ranking_legacy.py", "User Rankings"),
        ("pages/draft_results_legacy.py", "Draft Results"),
    ],
)
def test_legacy_url_redirects(
    fake_page_backend,
    legacy_page: str,
    expected_title: str,
) -> None:
    app = _authenticated_app(fake_page_backend)

    app.switch_page(legacy_page).run()

    _assert_page(app, expected_title)


@pytest.mark.parametrize(
    ("page_path", "expected_title"),
    [
        ("pages/overview.py", "Overview"),
        ("pages/draft_results.py", "Draft Results"),
        ("pages/transactions.py", "Transactions"),
        ("pages/players.py", "Players"),
        ("pages/matchups.py", "Matchups"),
        ("pages/ranking.py", "User Rankings"),
        ("pages/analysis.py", "Statistics"),
        ("pages/comparison.py", "Comparison"),
        ("pages/graphs.py", "Single Player Selection"),
        ("pages/team.py", "Team Page"),
    ],
)
def test_authenticated_page_renders(
    fake_page_backend,
    page_path: str,
    expected_title: str,
) -> None:
    app = _authenticated_app(fake_page_backend)

    app.switch_page(page_path).run()

    _assert_page(app, expected_title)


def test_analysis_mode_hides_overview_navigation_and_can_exit(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)

    app.switch_page("pages/analysis.py").run()

    _assert_page(app, "Statistics")
    assert app.session_state["_analysis_mode"] is True
    assert next(box for box in app.selectbox if box.label == "Team").value == "user-1"

    next(
        button for button in app.button if button.label == "Back to Overview"
    ).click().run()

    _assert_page(app, "Overview")
    assert "_analysis_mode" not in app.session_state


def test_statistics_filters_update_the_selected_view(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.switch_page("pages/analysis.py").run()

    position = next(box for box in app.selectbox if box.label == "Position")
    position.set_value("QB").run()
    period = next(
        control for control in app.segmented_control if control.label == "Period"
    )
    period.set_value("Week").run()
    week = next(box for box in app.selectbox if box.label == "Week")
    week.set_value(3).run()
    stats_source = next(
        control for control in app.segmented_control if control.label == "Stat type"
    )
    stats_source.set_value("Predicted").run()

    _assert_page(app, "Statistics")
    assert _query_value(app, "position") == "QB"
    assert _query_value(app, "period") == "week"
    assert _query_value(app, "week") == "3"
    assert _query_value(app, "stats") == "predicted"


def test_players_page_is_available_inside_analysis_mode(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.switch_page("pages/analysis.py").run()

    app.switch_page("pages/players.py").run()

    _assert_page(app, "Players")
    assert app.session_state["_analysis_mode"] is True
    assert any(button.label == "Back to Overview" for button in app.button)
    assert not any(button.label == "Switch Leagues" for button in app.button)

    next(
        button for button in app.button if button.label == "Back to Overview"
    ).click().run()

    _assert_page(app, "Overview")
    assert "_analysis_mode" not in app.session_state


def test_matchups_page_is_available_inside_analysis_mode(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.switch_page("pages/analysis.py").run()

    app.switch_page("pages/matchups.py").run()

    _assert_page(app, "Matchups")
    assert app.session_state["_analysis_mode"] is True
    assert any(button.label == "Back to Overview" for button in app.button)
    assert not any(button.label == "Switch Leagues" for button in app.button)

    next(
        button for button in app.button if button.label == "Back to Overview"
    ).click().run()

    _assert_page(app, "Overview")
    assert "_analysis_mode" not in app.session_state


def test_comparison_column_only_appears_in_analysis_state(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)

    app.switch_page("pages/players.py").run()
    assert COMPARISON_COLUMN not in app.dataframe[0].value.columns

    app.switch_page("pages/analysis.py").run()
    assert app.dataframe[0].value.columns[0] == COMPARISON_COLUMN

    app.switch_page("pages/players.py").run()
    assert app.dataframe[0].value.columns[0] == COMPARISON_COLUMN


@pytest.mark.parametrize("page_path", ["pages/analysis.py", "pages/players.py"])
def test_selected_players_appear_in_analysis_comparison_sidebar(
    fake_page_backend,
    page_path: str,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["_analysis_mode"] = True
    app.session_state["comparison-player-ids-league-1"] = ["player-1"]

    app.switch_page(page_path).run()

    assert any(header.value == "Comparison" for header in app.subheader)
    comparison_markup = " ".join(markdown.value for markdown in app.markdown)
    assert "First Quarterback" in comparison_markup
    assert "QB · BUF" in comparison_markup
    assert any(caption.value == "1/5" for caption in app.caption)


def test_comparison_page_only_shows_checked_players(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1"]

    app.switch_page("pages/comparison.py").run()

    _assert_page(app, "Comparison")
    assert [tab.label for tab in app.tabs[:4]] == [
        "Overview",
        "Performance Statistics",
        "Stat Graphs",
        "Week-to-week Graphs",
    ]
    assert app.session_state["_analysis_mode"] is True
    assert app.dataframe[0].value["Player ID"].tolist() == ["player-1"]


def test_comparison_performance_tables_include_players_and_position_average(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.session_state["generated-comparison-player-ids-league-1"] = [
        "player-1",
        "player-2",
    ]

    app.switch_page("pages/comparison.py").run()

    performance_tab_names = [
        "Core Performance Statistics",
        "Projection Accuracy",
        "Consistency",
        "Opportunity",
        "Efficiency",
        "Availability",
    ]
    assert [
        tab.label for tab in app.tabs if tab.label in performance_tab_names
    ] == performance_tab_names
    performance_table = app.dataframe[1].value
    assert "First Quarterback (QB)" in performance_table.columns
    assert "Second Quarterback (QB)" in performance_table.columns
    assert "QB League Average" in performance_table.columns
    assert not any(column.startswith("vs ") for column in performance_table.columns)


def test_comparison_performance_limits_mixed_position_groups_to_fantasy_points(
    monkeypatch,
    fake_page_backend,
) -> None:
    from fantasy_dashboard import data

    players = data.get_nfl_players()
    mixed_position_players = {
        player_id: dict(player) for player_id, player in players.items()
    }
    mixed_position_players["player-2"]["position"] = "WR"
    mixed_position_players["player-2"]["fantasy_positions"] = ["WR"]
    monkeypatch.setattr(data, "get_nfl_players", lambda: mixed_position_players)
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.session_state["generated-comparison-player-ids-league-1"] = [
        "player-1",
        "player-2",
    ]

    app.switch_page("pages/comparison.py").run()

    stat_selector = next(
        box
        for box in app.selectbox
        if box.key == "comparison-performance-league-1-stat"
    )
    assert stat_selector.options == ["Fantasy Points"]
    assert app.selectbox(key="comparison-graphs-league-1-stat").options == [
        "Fantasy Points"
    ]
    assert app.selectbox(key="comparison-weekly-graphs-league-1-stat").options == [
        "Fantasy Points"
    ]
    all_tab_labels = [tab.label for tab in app.tabs]
    performance_tab_names = [
        "Core Performance Statistics",
        "Projection Accuracy",
        "Consistency",
        "Opportunity",
        "Efficiency",
        "Availability",
    ]
    performance_tab_labels = [
        label for label in all_tab_labels if label in performance_tab_names
    ]
    assert "Opportunity" not in performance_tab_labels
    assert "Efficiency" not in performance_tab_labels
    assert performance_tab_labels == [
        "Core Performance Statistics",
        "Projection Accuracy",
        "Consistency",
        "Availability",
    ]
    graph_metric_labels = [
        checkbox.label
        for checkbox in app.checkbox
        if " · " in checkbox.label
        and str(checkbox.key).startswith("comparison-graphs-")
    ]
    assert not any(label.startswith("Opportunity ·") for label in graph_metric_labels)
    assert not any(label.startswith("Efficiency ·") for label in graph_metric_labels)
    assert not any(label.startswith("Availability ·") for label in graph_metric_labels)
    assert any("different position groups" in warning.value for warning in app.warning)


def test_comparison_can_show_union_of_relevant_position_stats(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1"]
    app.switch_page("pages/comparison.py").run()

    next(
        checkbox for checkbox in app.checkbox if checkbox.label == "Only Relevant Stats"
    ).check().run()

    columns = app.dataframe[0].value.columns
    assert "Fantasy Points" in columns
    assert "Pass Yds" in columns
    assert "Receptions" not in columns
    assert _query_value(app, "relevant") == "true"


@pytest.mark.parametrize(
    "page_path",
    ["pages/players.py", "pages/analysis.py", "pages/comparison.py"],
)
def test_position_filters_include_flex(
    fake_page_backend,
    page_path: str,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1"]
    app.switch_page(page_path).run()

    position = next(box for box in app.selectbox if box.label == "Position")
    assert "FLEX" in position.options


def test_comparison_tabs_require_generate_comparisons(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1"]
    app.switch_page("pages/comparison.py").run()

    assert not any(box.label == "Stat" for box in app.selectbox)
    assert (
        sum("Press Generate Comparisons" in warning.value for warning in app.warning)
        == 3
    )


def test_generate_comparisons_snapshots_visible_checked_players(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.switch_page("pages/comparison.py").run()

    next(
        button for button in app.button if button.label == "Generate Comparisons"
    ).click().run()

    _assert_page(app, "Comparison")
    assert app.session_state["generated-comparison-player-ids-league-1"] == [
        "player-1",
        "player-2",
    ]
    assert any(box.label == "Stat" for box in app.selectbox)


def test_generate_comparisons_uses_only_rows_visible_after_filtering(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.switch_page("pages/comparison.py").run()
    next(box for box in app.selectbox if box.label == "Position").set_value(
        "FLEX"
    ).run()

    next(
        button for button in app.button if button.label == "Generate Comparisons"
    ).click().run()

    _assert_page(app, "Comparison")
    assert app.session_state["generated-comparison-player-ids-league-1"] == []


def test_comparison_graphs_offer_week_and_statistic_controls(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.session_state["generated-comparison-player-ids-league-1"] = [
        "player-1",
        "player-2",
    ]

    app.switch_page("pages/comparison.py").run()

    graph_year = app.selectbox(key="comparison-graphs-league-1-year")
    assert graph_year.value == "2026"
    graph_stat = app.selectbox(key="comparison-graphs-league-1-stat")
    assert graph_stat.value == "Fantasy Points"
    assert "Pass Yds" in graph_stat.options
    assert "Receptions" not in graph_stat.options
    week_checkboxes = [
        checkbox for checkbox in app.checkbox if checkbox.label.startswith("Week ")
    ]
    assert len(week_checkboxes) == 18
    assert all(checkbox.value for checkbox in week_checkboxes)

    next(
        button for button in app.button if button.label == "Check/Uncheck All"
    ).click().run()

    week_checkboxes = [
        checkbox for checkbox in app.checkbox if checkbox.label.startswith("Week ")
    ]
    assert not any(checkbox.value for checkbox in week_checkboxes)
    assert any("Select at least one week" in warning.value for warning in app.warning)


def test_comparison_graphs_limit_statistics_and_render_bars(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.session_state["generated-comparison-player-ids-league-1"] = [
        "player-1",
        "player-2",
    ]
    metric_prefix = "comparison-graphs-league-1-2026-metric-Core Performance:"
    for metric_key in [
        "average",
        "median",
        "standard_deviation",
        "floor_25",
        "ceiling_75",
        "ceiling_90",
    ]:
        app.session_state[f"{metric_prefix}{metric_key}"] = True

    app.switch_page("pages/comparison.py").run()

    metric_checkboxes = [
        checkbox for checkbox in app.checkbox if " · " in checkbox.label
    ]
    assert sum(bool(checkbox.value) for checkbox in metric_checkboxes) == 5
    assert app.get("vega_lite_chart")


def test_comparison_weekly_graphs_use_performance_metrics_without_week_filters(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["comparison-player-ids-league-1"] = ["player-1", "player-2"]
    app.session_state["generated-comparison-player-ids-league-1"] = [
        "player-1",
        "player-2",
    ]
    app.session_state[
        "comparison-weekly-graphs-league-1-2026-metric-Core Performance:average"
    ] = True

    app.switch_page("pages/comparison.py").run()

    assert app.selectbox(key="comparison-weekly-graphs-league-1-year").value == "2026"
    weekly_stat = app.selectbox(key="comparison-weekly-graphs-league-1-stat")
    assert weekly_stat.value == "Fantasy Points"
    assert "Pass Yds" in weekly_stat.options
    assert "Receptions" not in weekly_stat.options
    assert not any(
        str(checkbox.key).startswith("comparison-weekly-graphs-league-1-2026-week")
        for checkbox in app.checkbox
    )
    weekly_metric_labels = [
        checkbox.label
        for checkbox in app.checkbox
        if str(checkbox.key).startswith("comparison-weekly-graphs-league-1-2026-metric")
    ]
    assert any(label.startswith("Core Performance ·") for label in weekly_metric_labels)
    assert any(label.startswith("Opportunity ·") for label in weekly_metric_labels)
    assert any(label.startswith("Efficiency ·") for label in weekly_metric_labels)
    assert any(label.startswith("Availability ·") for label in weekly_metric_labels)
    assert app.get("vega_lite_chart")


def test_graphs_page_is_a_searchable_player_picker(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.switch_page("pages/graphs.py").run()

    _assert_page(app, "Single Player Selection")
    assert not app.tabs
    assert any(field.label == "Player name" for field in app.text_input)
    assert app.dataframe[0].value.columns.tolist() == [
        "Player ID",
        "Player",
        "Graph",
    ]


def test_graph_player_opens_player_stats_state_and_can_return(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["_graph_target_player_id"] = "player-1"

    app.switch_page("pages/graphs.py").run()

    _assert_page(app, "Graph")
    assert app.session_state["_player_stats_mode"] is True
    assert any(header.value == "First Quarterback" for header in app.header)
    assert any(button.label == "Back to Analysis" for button in app.button)

    next(
        button for button in app.button if button.label == "Back to Analysis"
    ).click().run()

    _assert_page(app, "Single Player Selection")
    assert "_player_stats_mode" not in app.session_state
    assert app.session_state["_analysis_mode"] is True


def test_graph_controls_offer_recent_years_and_relevant_player_stats(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/graph.py").run()

    year = next(box for box in app.selectbox if box.label == "Year")
    stat = next(box for box in app.selectbox if box.label == "Stat")
    assert year.options == ["2026", "2025", "2024"]
    assert year.value == "2026"
    assert stat.value == "Fantasy Points"
    assert "Pass Yds" in stat.options
    assert "FG Made" not in stat.options
    assert not any(control.label == "Stat type" for control in app.segmented_control)

    year.set_value("2025").run()
    stat.set_value("Pass Yds").run()

    _assert_page(app, "Graph")
    assert _query_value(app, "year") == "2025"
    assert _query_value(app, "stat") == "Pass Yds"
    assert "source" not in app.query_params


def test_graph_recovers_from_empty_persisted_control_values(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.session_state["graph-league-1-player-1-year"] = None
    app.session_state["graph-league-1-player-1-stat"] = None
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/graph.py").run()

    _assert_page(app, "Graph")
    assert next(box for box in app.selectbox if box.label == "Year").value == "2026"
    assert (
        next(box for box in app.selectbox if box.label == "Stat").value
        == "Fantasy Points"
    )


def test_player_stats_state_includes_full_stats_page(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/stats.py").run()

    _assert_page(app, "Stats")
    assert app.session_state["_player_stats_mode"] is True
    assert any(header.value == "First Quarterback" for header in app.header)
    assert {"Week", "Opponent", "Fantasy Points"}.issubset(
        app.dataframe[0].value.columns
    )
    assert app.dataframe[0].value["Opponent"].tolist() == ["NYJ"]
    assert next(box for box in app.selectbox if box.label == "Year").options == [
        "2026",
        "2025",
        "2024",
    ]
    assert (
        next(
            control for control in app.segmented_control if control.label == "Stat type"
        ).value
        == "Actual"
    )
    assert (
        next(
            toggle for toggle in app.toggle if toggle.label == "Only Relevant Stats"
        ).value
        is False
    )
    assert any(button.label == "Back to Analysis" for button in app.button)


def test_player_stats_state_includes_core_performance(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/performance.py").run()

    _assert_page(app, "Performance")
    assert app.session_state["_player_stats_mode"] is True
    assert any(header.value == "First Quarterback" for header in app.header)
    assert [tab.label for tab in app.tabs] == [
        "Core Performance Statistics",
        "Projection Accuracy",
        "Consistency",
        "Opportunity",
        "Efficiency",
        "Availability",
    ]
    year_selector = next(box for box in app.selectbox if box.label == "Year")
    assert year_selector.value == "2026"
    assert year_selector.options == ["2026", "2025", "2024"]
    stat_selector = next(box for box in app.selectbox if box.label == "Stat")
    assert stat_selector.value == "Fantasy Points"
    assert stat_selector.options == [
        "Fantasy Points",
        "Pass Att",
        "Completions",
        "Pass Yds",
        "Pass TD",
        "Pass INT",
        "Rush Yds",
        "Rush TD",
    ]
    assert app.dataframe[0].value["Statistic"].tolist() == [
        "μ",
        "Median",
        "σ",
        "Q25",
        "Q75",
        "Q90",
        "Season total",
        "Games played",
        "Last-1-game average",
        "Recent difference from season average",
        "Recent percent change",
        "Best week",
        "Worst week",
    ]
    assert app.dataframe[0].value["View Graph"].tolist() == ["View"] * 13
    assert "QB League Average" in app.dataframe[0].value.columns
    assert "vs QB Average" in app.dataframe[0].value.columns
    assert app.dataframe[1].value["Statistic"].tolist() == [
        "Actual average",
        "Predicted average",
        "MAE",
        "Bias",
        "RMSE",
        "Hit rate",
        "r",
    ]
    assert "QB League Average" in app.dataframe[1].value.columns
    assert "vs QB Average" in app.dataframe[1].value.columns
    assert app.dataframe[1].value["View Graph"].tolist() == ["View"] * 7
    assert app.dataframe[2].value["Statistic"].tolist() == [
        "Consistency rate",
        "Boom rate",
        "Bust rate",
        "Rolling 3-game average",
        "Trend slope",
    ]
    assert "QB League Average" in app.dataframe[2].value.columns
    assert "vs QB Average" in app.dataframe[2].value.columns
    assert app.dataframe[2].value["View Graph"].tolist() == ["View"] * 5
    assert (
        next(
            control for control in app.number_input if control.label == "Hit tolerance"
        ).value
        == 3.0
    )
    assert (
        next(
            control
            for control in app.number_input
            if control.label == "Consistency band (%)"
        ).value
        == 20.0
    )
    assert app.dataframe[3].value["Statistic"].tolist() == [
        "Pass attempts",
        "Snap share",
        "Red-zone opportunities",
    ]
    assert "QB League Average" in app.dataframe[3].value.columns
    assert "View Graph" in app.dataframe[3].value.columns
    assert app.dataframe[4].value["Statistic"].tolist() == [
        "Completion rate",
        "Yards per pass attempt",
        "Passing touchdown rate",
        "Interception rate",
    ]
    assert "QB League Average" in app.dataframe[4].value.columns
    assert "View Graph" in app.dataframe[4].value.columns
    assert app.dataframe[5].value["Statistic"].tolist() == [
        "Games played",
        "Games missed",
        "Availability rate",
        "Injury status",
    ]
    assert "QB League Average" in app.dataframe[5].value.columns
    assert "View Graph" in app.dataframe[5].value.columns
    assert any(button.label == "Back to Analysis" for button in app.button)


def test_core_performance_graph_opens_for_selected_statistic(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.session_state["_performance_core_graph_metric_key"] = "average"
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/performance.py").run()

    _assert_page(app, "Performance")
    assert app.get("vega_lite_chart")
    assert any(
        subheader.value == "Average · Fantasy Points" for subheader in app.subheader
    )


@pytest.mark.parametrize(
    ("state_key", "metric_key", "expected_subheader"),
    [
        (
            "_performance_projection_graph_metric_key",
            "mae",
            "MAE · Fantasy Points",
        ),
        (
            "_performance_consistency_graph_metric_key",
            "consistency_rate",
            "Consistency rate · Fantasy Points",
        ),
        (
            "_performance_opportunity_graph_metric_key",
            "pass_attempts",
            "Pass attempts · Attempts",
        ),
        (
            "_performance_efficiency_graph_metric_key",
            "completion_rate",
            "Completion rate · %",
        ),
        (
            "_performance_availability_graph_metric_key",
            "games_played",
            "Games played · Games",
        ),
    ],
)
def test_additional_performance_graphs_open_for_selected_statistic(
    fake_page_backend,
    state_key: str,
    metric_key: str,
    expected_subheader: str,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.session_state[state_key] = metric_key
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/performance.py").run()

    _assert_page(app, "Performance")
    assert app.get("vega_lite_chart")
    assert any(subheader.value == expected_subheader for subheader in app.subheader)


def test_player_stats_state_includes_recent_news_page(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.query_params["player_id"] = "player-1"

    app.switch_page("pages/news.py").run()

    _assert_page(app, "News")
    assert app.session_state["_player_stats_mode"] is True
    assert any(caption.value == "First Quarterback" for caption in app.caption)
    assert any(subheader.value == "Smoke Test News" for subheader in app.subheader)
    assert any("By Example Writer" in caption.value for caption in app.caption)
    assert app.get("link_button")
    assert not any(
        text.value == "A deterministic player update." for text in app.markdown
    )
    assert any(button.label == "Back to Analysis" for button in app.button)


def test_player_stats_page_supports_predictions_and_relevant_stats(
    fake_page_backend,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["graph_player_id"] = "player-1"
    app.session_state["_player_stats_mode"] = True
    app.query_params["player_id"] = "player-1"
    app.switch_page("pages/stats.py").run()

    source = next(
        control for control in app.segmented_control if control.label == "Stat type"
    )
    source.set_value("Predicted").run()
    relevant = next(
        toggle for toggle in app.toggle if toggle.label == "Only Relevant Stats"
    )
    relevant.set_value(True).run()

    _assert_page(app, "Stats")
    columns = app.dataframe[0].value.columns
    assert "Opponent" in columns
    assert "Pass Yds" in columns
    assert "Receptions" not in columns
    assert _query_value(app, "stats") == "predicted"
    assert _query_value(app, "relevant") == "true"


@pytest.mark.parametrize(
    ("page_path", "state_key"),
    [
        ("pages/players.py", "_selected_news_player_id"),
        ("pages/analysis.py", "_statistics_news_player_id"),
    ],
)
def test_statistics_tables_open_recent_player_news(
    fake_page_backend,
    page_path: str,
    state_key: str,
) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state[state_key] = "player-1"

    app.switch_page(page_path).run()

    assert not app.exception
    assert any(subheader.value == "Smoke Test News" for subheader in app.subheader)


def test_matchups_handles_empty_week(monkeypatch, fake_page_backend) -> None:
    from fantasy_dashboard import data

    monkeypatch.setattr(
        data,
        "get_weekly_matchups",
        lambda *args: WeeklyMatchupContainer.from_api([]),
    )
    app = _authenticated_app(fake_page_backend)

    app.switch_page("pages/matchups.py").run()

    _assert_page(app, "Matchups")
    assert any("No matchups" in info.value for info in app.info)


def test_matchup_week_and_prediction_controls_rerun(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.switch_page("pages/matchups.py").run()

    week_key = "matchup-week-v3-league-1-2026"
    app.selectbox(key=week_key).set_value(2).run()
    stat_type = next(
        control for control in app.segmented_control if control.label == "Stat type"
    )
    stat_type.set_value("Predicted").run()

    _assert_page(app, "Matchups")
    assert app.selectbox(key=week_key).value == 2
    assert stat_type.value == "Predicted"
    assert _query_value(app, "league_id") == "league-1"
    assert _query_value(app, "week") == "2"
    assert _query_value(app, "stats") == "predicted"


def test_players_deep_link_restores_filters(fake_page_backend) -> None:
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.session_state["sleeper_user"] = fake_page_backend
    app.run()
    app.switch_page("pages/players.py")
    app.query_params["league_id"] = "league-1"
    app.query_params["availability"] = "available"
    app.query_params["position"] = "QB"
    app.query_params["period"] = "week"
    app.query_params["week"] = "3"
    app.query_params["stats"] = "predicted"
    app.query_params["search"] = "First"
    app.run()

    _assert_page(app, "Players")
    assert next(
        toggle for toggle in app.toggle if toggle.label == "Available players only"
    ).value
    assert next(box for box in app.selectbox if box.label == "Position").value == "QB"
    assert next(box for box in app.selectbox if box.label == "Week").value == 3
    assert (
        next(
            control for control in app.segmented_control if control.label == "Stat type"
        ).value
        == "Predicted"
    )
    assert (
        next(
            control for control in app.segmented_control if control.label == "Period"
        ).value
        == "Week"
    )
    assert (
        next(field for field in app.text_input if field.label == "Player name").value
        == "First"
    )


def test_players_recovers_from_empty_segmented_controls(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["players-league-1-period"] = None
    app.session_state["players-league-1-stat-source"] = None

    app.switch_page("pages/players.py").run()

    _assert_page(app, "Players")
    assert (
        next(
            control for control in app.segmented_control if control.label == "Period"
        ).value
        == "Season"
    )
    assert (
        next(
            control for control in app.segmented_control if control.label == "Stat type"
        ).value
        == "Actual"
    )
    assert _query_value(app, "period") == "season"
    assert _query_value(app, "stats") == "actual"


def test_matchup_player_details_and_relevant_stats_open(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.switch_page("pages/matchups.py").run()
    player_button = next(
        button
        for button in app.button
        if str(button.key).startswith("matchup-player-button-")
    )

    player_button.click().run()

    assert not app.exception
    assert any(header.value == "First Quarterback" for header in app.header)
    assert any(button.label == "View Recent News" for button in app.button)
    stats_control = next(
        control for control in app.segmented_control if control.label == "Stats shown"
    )
    stats_control.set_value("Relevant Stats").run()
    assert not app.exception
    assert stats_control.value == "Relevant Stats"


def test_matchup_player_recent_news_opens(fake_page_backend) -> None:
    app = _authenticated_app(fake_page_backend)
    app.session_state["matchups_news_player_id"] = "player-1"
    app.switch_page("pages/matchups.py").run()

    assert not app.exception
    assert any(subheader.value == "Smoke Test News" for subheader in app.subheader)
