from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
