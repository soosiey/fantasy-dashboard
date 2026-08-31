import base64

import pytest

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
        "player-1": {"pass_yd": 250, "pass_td": 2},
        "player-2": {"pass_yd": 220, "pass_td": 1},
    }
    draft = DraftPickContainer.from_api(
        [
            {
                "pick_no": 1,
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
