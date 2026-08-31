import base64
from collections.abc import Callable
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fantasy_dashboard import data
from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.components import player_news
from fantasy_dashboard.models.bracket import BracketContainer
from fantasy_dashboard.models.draft import DraftPickContainer
from fantasy_dashboard.models.league import (
    LeagueContainer,
    LeagueModel,
    RosterContainer,
)
from fantasy_dashboard.models.matchup import WeeklyMatchupContainer
from fantasy_dashboard.models.news import PlayerNewsModel
from fantasy_dashboard.models.transaction import TransactionContainer
from fantasy_dashboard.models.user import SleeperUser, UserContainer

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def fake_page_backend(monkeypatch, tmp_path) -> SleeperUser:
    """Replace every page data source with one small, deterministic league."""
    user = SleeperUser("user-1", "test_user", "Test User", "avatar-1")
    monkeypatch.setattr(
        data,
        "MANUAL_REFRESH_STATE_PATH",
        tmp_path / "manual_refresh.json",
    )
    league = LeagueModel.from_api(
        {
            "league_id": "league-1",
            "total_rosters": 2,
            "status": "in_season",
            "sport": "nfl",
            "settings": {
                "waiver_budget": 100,
                "playoff_teams": 2,
                "num_teams": 2,
                "playoff_week_start": 15,
                "waiver_day_of_week": 2,
                "trade_deadline": 11,
                "reserve_slots": 1,
            },
            "roster_positions": ["QB", "BN"],
            "name": "Smoke Test League",
            "draft_id": "draft-1",
            "scoring_settings": {"pass_yd": 0.04, "pass_td": 4},
            "bracket_id": "winners-1",
            "loser_bracket_id": "losers-1",
            "avatar": "league-avatar",
            "season": "2026",
            "season_type": "regular",
        }
    )
    leagues = LeagueContainer([league])
    users = UserContainer.from_api(
        [
            {
                "user_id": "user-1",
                "display_name": "Test User",
                "avatar": "avatar-1",
                "metadata": {"team_name": "Test Team"},
            },
            {
                "user_id": "user-2",
                "display_name": "Other User",
                "avatar": "avatar-2",
                "metadata": {"team_name": "Other Team"},
            },
        ]
    )
    rosters = RosterContainer.from_api(
        [
            {
                "starters": ["player-1"],
                "players": ["player-1"],
                "roster_id": 1,
                "owner_id": "user-1",
                "league_id": "league-1",
                "reserve": [],
                "settings": {
                    "wins": 1,
                    "losses": 0,
                    "ties": 0,
                    "waiver_position": 1,
                    "waiver_budget_used": 0,
                    "total_moves": 1,
                    "fpts": 20,
                    "fpts_decimal": 0,
                    "fpts_against": 10,
                    "fpts_against_decimal": 0,
                },
            },
            {
                "starters": ["player-2"],
                "players": ["player-2"],
                "roster_id": 2,
                "owner_id": "user-2",
                "league_id": "league-1",
                "reserve": [],
                "settings": {
                    "wins": 0,
                    "losses": 1,
                    "ties": 0,
                    "waiver_position": 2,
                    "waiver_budget_used": 5,
                    "total_moves": 1,
                    "fpts": 10,
                    "fpts_decimal": 0,
                    "fpts_against": 20,
                    "fpts_against_decimal": 0,
                },
            },
        ]
    )
    matchups = WeeklyMatchupContainer.from_api(
        [
            {
                "starters": ["player-1"],
                "players": ["player-1"],
                "roster_id": 1,
                "matchup_id": 1,
                "points": 14,
                "players_points": {"player-1": 14},
            },
            {
                "starters": ["player-2"],
                "players": ["player-2"],
                "roster_id": 2,
                "matchup_id": 1,
                "points": 12,
                "players_points": {"player-2": 12},
            },
        ]
    )
    players = {
        "player-1": {
            "player_id": "player-1",
            "first_name": "First",
            "last_name": "Quarterback",
            "position": "QB",
            "fantasy_positions": ["QB"],
            "team": "BUF",
            "number": 1,
            "depth_chart_order": 1,
            "injury_status": "",
            "rotoworld_id": 101,
            "active": True,
        },
        "player-2": {
            "player_id": "player-2",
            "first_name": "Second",
            "last_name": "Quarterback",
            "position": "QB",
            "fantasy_positions": ["QB"],
            "team": "NYJ",
            "number": 2,
            "depth_chart_order": 1,
            "injury_status": "",
            "rotoworld_id": 102,
            "active": True,
        },
    }
    stats = {
        "player-1": {
            "pass_att": 30,
            "pass_cmp": 20,
            "pass_yd": 250,
            "pass_td": 2,
            "pass_int": 1,
            "off_snp": 60,
            "tm_off_snp": 60,
            "pass_rz_att": 3,
            "rush_rz_att": 1,
        },
        "player-2": {
            "pass_att": 28,
            "pass_cmp": 18,
            "pass_yd": 220,
            "pass_td": 1,
            "pass_int": 0,
            "off_snp": 58,
            "tm_off_snp": 60,
            "pass_rz_att": 2,
            "rush_rz_att": 0,
        },
    }
    draft = DraftPickContainer.from_api(
        [
            {
                "pick_no": 1,
                "round": 1,
                "player_id": "player-1",
                "picked_by": "user-1",
                "metadata": {
                    "first_name": "First",
                    "last_name": "Quarterback",
                    "amount": "25",
                },
            }
        ]
    )
    transactions = TransactionContainer.from_api(
        [
            {
                "transaction_id": "transaction-1",
                "type": "free_agent",
                "creator": "user-1",
                "created": 1,
                "adds": {"player-1": 1},
            }
        ]
    )
    empty_bracket = BracketContainer.from_api([])
    pixel = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    # Keep both the app entrypoint and every page fully offline.
    monkeypatch.setattr(
        SleeperClient,
        "refresh_nfl_players_cache",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(data, "get_user", lambda username: user)
    monkeypatch.setattr(data, "get_current_nfl_season", lambda: "2026")
    monkeypatch.setattr(data, "get_default_nfl_week", lambda season: 1)
    monkeypatch.setattr(data, "get_leagues", lambda *args: leagues)
    monkeypatch.setattr(data, "get_league", lambda league_id: league)
    monkeypatch.setattr(data, "get_league_users", lambda league_id: users)
    monkeypatch.setattr(data, "get_rosters", lambda league_id: rosters)
    monkeypatch.setattr(data, "get_weekly_matchups", lambda *args: matchups)
    monkeypatch.setattr(
        data,
        "get_weekly_matchup_schedules",
        lambda league_id, start_week, end_week: (
            {week: matchups for week in range(start_week, end_week + 1)},
            [],
        ),
    )
    monkeypatch.setattr(data, "get_nfl_players", lambda: players)
    monkeypatch.setattr(data, "get_player_stats", lambda *args: stats)
    monkeypatch.setattr(data, "get_projected_player_stats", lambda *args: stats)
    monkeypatch.setattr(
        data,
        "get_player_weekly_stats",
        lambda *args: {1: {"week": 1, "opponent": "NYJ", "stats": stats["player-1"]}},
    )
    monkeypatch.setattr(data, "get_nfl_schedule", lambda *args: [])
    monkeypatch.setattr(data, "get_trending_players", lambda *args: [])
    monkeypatch.setattr(data, "get_draft_picks", lambda draft_id: draft)
    monkeypatch.setattr(data, "get_league_transactions", lambda league_id: transactions)
    monkeypatch.setattr(data, "get_winners_bracket", lambda league_id: empty_bracket)
    monkeypatch.setattr(data, "get_losers_bracket", lambda league_id: empty_bracket)
    monkeypatch.setattr(data, "get_avatar", lambda avatar_id: pixel)
    monkeypatch.setattr(data, "get_data_update", lambda *args: None)
    monkeypatch.setattr(
        data,
        "refresh_current_week_input_data",
        lambda *args, **kwargs: ("2026", "regular", 1),
    )
    monkeypatch.setattr(
        player_news,
        "_get_recent_news_v4",
        lambda *args: [
            PlayerNewsModel(
                title="Smoke Test News",
                date="2026-08-28T12:00:00Z",
                author="Example Writer",
                source_url="https://www.nbcsports.com/fantasy/football/player-news",
            )
        ],
    )

    return user


@pytest.fixture
def realistic_page_backend(
    monkeypatch,
    fake_page_backend: SleeperUser,
) -> SleeperUser:
    """Extend the offline backend with every fantasy position and week state."""
    league = LeagueModel.from_api(
        {
            "league_id": "league-1",
            "total_rosters": 2,
            "status": "in_season",
            "sport": "nfl",
            "settings": {
                "waiver_budget": 100,
                "playoff_teams": 2,
                "num_teams": 2,
                "playoff_week_start": 15,
                "waiver_day_of_week": 2,
                "trade_deadline": 11,
                "reserve_slots": 2,
            },
            "roster_positions": ["QB", "RB", "WR", "TE", "FLEX", "K", "DEF", "BN"],
            "name": "Realistic Test League",
            "draft_id": "draft-1",
            "scoring_settings": {
                "pass_yd": 0.04,
                "pass_td": 4,
                "rush_yd": 0.1,
                "rush_td": 6,
                "rec": 1,
                "rec_yd": 0.1,
                "rec_td": 6,
                "fgm": 3,
                "xpm": 1,
                "sack": 1,
                "int": 2,
                "fum_rec": 2,
                "def_td": 6,
            },
            "bracket_id": "winners-1",
            "loser_bracket_id": "losers-1",
            "avatar": "league-avatar",
            "season": "2026",
            "season_type": "regular",
        }
    )
    player_specs = [
        ("qb-1", "Quinn", "Quarterback", "QB", "BUF"),
        ("rb-1", "Riley", "Runner", "RB", "NYJ"),
        ("wr-1", "Will", "Receiver", "WR", "MIA"),
        ("te-1", "Taylor", "End", "TE", "NE"),
        ("k-1", "Kai", "Kicker", "K", "KC"),
        ("def-1", "Denver", "Defense", "DEF", "DEN"),
    ]
    players = {
        player_id: {
            "player_id": player_id,
            "first_name": first_name,
            "last_name": last_name,
            "position": position,
            "fantasy_positions": [position],
            "team": team,
            "number": index,
            "depth_chart_order": 1,
            "injury_status": "",
            "active": True,
        }
        for index, (player_id, first_name, last_name, position, team) in enumerate(
            player_specs,
            start=1,
        )
    }
    week_one_stats = {
        "qb-1": {"gp": 1, "pass_att": 32, "pass_cmp": 22, "pass_yd": 280, "pass_td": 2},
        "rb-1": {
            "gp": 1,
            "rush_att": 18,
            "rush_yd": 92,
            "rec_tgt": 4,
            "rec": 3,
            "rec_yd": 24,
        },
        "wr-1": {"gp": 1, "rec_tgt": 9, "rec": 6, "rec_yd": 88, "rec_td": 1},
        "te-1": {"gp": 1, "rec_tgt": 6, "rec": 5, "rec_yd": 54},
        "k-1": {"gp": 1, "fga": 3, "fgm": 2, "xpa": 3, "xpm": 3},
        "def-1": {"gp": 1, "sack": 4, "int": 1, "fum_rec": 1, "pts_allow": 17},
    }
    week_two_projections = {
        player_id: {
            stat_name: stat_value
            for stat_name, stat_value in player_stats.items()
            if stat_name != "gp"
        }
        for player_id, player_stats in week_one_stats.items()
    }
    rosters = RosterContainer.from_api(
        [
            {
                "starters": ["qb-1", "rb-1", "wr-1"],
                "players": ["qb-1", "rb-1", "wr-1"],
                "roster_id": 1,
                "owner_id": "user-1",
                "league_id": "league-1",
                "reserve": [],
                "settings": {
                    "wins": 1,
                    "losses": 0,
                    "ties": 0,
                    "waiver_position": 1,
                    "waiver_budget_used": 0,
                    "total_moves": 1,
                    "fpts": 50,
                    "fpts_decimal": 0,
                    "fpts_against": 40,
                    "fpts_against_decimal": 0,
                },
            },
            {
                "starters": ["te-1", "k-1", "def-1"],
                "players": ["te-1", "k-1", "def-1"],
                "roster_id": 2,
                "owner_id": "user-2",
                "league_id": "league-1",
                "reserve": [],
                "settings": {
                    "wins": 0,
                    "losses": 1,
                    "ties": 0,
                    "waiver_position": 2,
                    "waiver_budget_used": 5,
                    "total_moves": 1,
                    "fpts": 40,
                    "fpts_decimal": 0,
                    "fpts_against": 50,
                    "fpts_against_decimal": 0,
                },
            },
        ]
    )
    schedule = [
        {"week": 1, "home": "BUF", "away": "NYJ", "status": "complete"},
        {"week": 1, "home": "MIA", "away": "NE", "status": "complete"},
        {"week": 1, "home": "KC", "away": "DEN", "status": "complete"},
        {"week": 2, "home": "BUF", "away": "MIA", "status": "pre_game"},
        {"week": 2, "home": "NYJ", "away": "NE", "status": "pre_game"},
        {"week": 2, "home": "KC", "away": "DEN", "status": "pre_game"},
    ]

    monkeypatch.setattr(data, "get_league", lambda league_id: league)
    monkeypatch.setattr(data, "get_leagues", lambda *args: LeagueContainer([league]))
    monkeypatch.setattr(data, "get_rosters", lambda league_id: rosters)
    monkeypatch.setattr(data, "get_nfl_players", lambda: players)
    monkeypatch.setattr(data, "get_default_nfl_week", lambda season: 2)
    monkeypatch.setattr(
        data,
        "get_player_stats",
        lambda season, season_type="regular", week=None: (
            week_one_stats if week in {None, 1} else {}
        ),
    )
    monkeypatch.setattr(
        data,
        "get_projected_player_stats",
        lambda season, week=None: (
            week_two_projections if week in {None, 2} else week_one_stats
        ),
    )
    monkeypatch.setattr(
        data,
        "get_player_weekly_stats",
        lambda player_id, *args: (
            {
                1: {
                    "week": 1,
                    "opponent": "OPP",
                    "stats": week_one_stats[player_id],
                }
            }
            if player_id in week_one_stats
            else {}
        ),
    )
    monkeypatch.setattr(data, "get_nfl_schedule", lambda *args: schedule)
    monkeypatch.setattr(
        data,
        "refresh_current_week_input_data",
        lambda *args, **kwargs: ("2026", "regular", 2),
    )
    return fake_page_backend


def _create_authenticated_app(user: SleeperUser) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.session_state["sleeper_user"] = user
    app.session_state["league_id"] = "league-1"
    app.session_state["user_id"] = "user-1"
    app.query_params["league_id"] = "league-1"
    return app.run()


@pytest.fixture
def authenticated_app(
    fake_page_backend: SleeperUser,
) -> Callable[[], AppTest]:
    """Create a fresh app already logged into the deterministic test league."""

    def create_app() -> AppTest:
        return _create_authenticated_app(fake_page_backend)

    return create_app


@pytest.fixture
def realistic_authenticated_app(
    realistic_page_backend: SleeperUser,
) -> Callable[[], AppTest]:
    """Create a logged-in app backed by the six-position realistic league."""

    def create_app() -> AppTest:
        return _create_authenticated_app(realistic_page_backend)

    return create_app
