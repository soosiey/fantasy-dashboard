from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fantasy_dashboard.models.matchup import WeeklyMatchupContainer

pytestmark = pytest.mark.smoke
APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _authenticated_app(fake_page_backend) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.session_state["sleeper_user"] = fake_page_backend
    app.session_state["league_id"] = "league-1"
    app.session_state["user_id"] = "user-1"
    app.session_state["team_id"] = "team-1"
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

    app.selectbox(key="matchup-week-v2-2026").set_value(2).run()
    stat_type = next(
        control for control in app.segmented_control if control.label == "Stat type"
    )
    stat_type.set_value("Predicted").run()

    _assert_page(app, "Matchups")
    assert app.selectbox(key="matchup-week-v2-2026").value == 2
    assert stat_type.value == "Predicted"


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
