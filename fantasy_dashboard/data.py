import json
from pathlib import Path
from typing import Any

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.models.bracket import BracketContainer
from fantasy_dashboard.models.league import (
    LeagueContainer,
    LeagueModel,
    RosterContainer,
)
from fantasy_dashboard.models.matchup import WeeklyMatchupContainer
from fantasy_dashboard.models.user import SleeperUser, UserContainer
from fantasy_dashboard.paths import NFL_PLAYERS_PATH


# Share the stateless Sleeper client across sessions and page reruns.
@st.cache_resource
def get_sleeper_client() -> SleeperClient:
    return SleeperClient()


# Cache account and league-list lookups that rarely change during a session.
@st.cache_data(ttl=3600, show_spinner=False)
def get_user(username: str) -> SleeperUser | None:
    return get_sleeper_client().get_user(username)


@st.cache_data(ttl=1800, show_spinner=False)
def get_leagues(
    user_id: str, season: str, sport: str = "nfl"
) -> LeagueContainer | None:
    return get_sleeper_client().get_leagues(user_id, season, sport)


# Cache stable league configuration longer than live roster and matchup data.
@st.cache_data(ttl=1800, show_spinner=False)
def get_league(league_id: str) -> LeagueModel | None:
    return get_sleeper_client().get_single_league(league_id)


@st.cache_data(ttl=600, show_spinner=False)
def get_league_users(league_id: str) -> UserContainer | None:
    return get_sleeper_client().get_all_users(league_id)


@st.cache_data(ttl=5, show_spinner=False)
def get_rosters(league_id: str) -> RosterContainer | None:
    return get_sleeper_client().get_all_rosters(league_id)


# Keep live scores and playoff progression fresh while avoiding rerun requests.
@st.cache_data(ttl=5, max_entries=128, show_spinner=False)
def get_weekly_matchups(
    league_id: str, week: int
) -> WeeklyMatchupContainer:
    return get_sleeper_client().get_matchups(league_id, week)


@st.cache_data(ttl=5, max_entries=64, show_spinner=False)
def get_player_stats(
    season: str,
    season_type: str = "regular",
    week: int | None = None,
) -> dict[str, dict]:
    return get_sleeper_client().get_player_stats(season, season_type, week)


@st.cache_data(ttl=5, max_entries=256, show_spinner=False)
def get_player_weekly_stats(
    player_id: str,
    season: str,
    season_type: str = "regular",
) -> dict[int, dict]:
    return get_sleeper_client().get_player_weekly_stats(
        player_id, season, season_type
    )


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def get_trending_players(
    trend_type: str,
    lookback_hours: int = 48,
    limit: int = 25,
) -> list[dict[str, int | str]]:
    return get_sleeper_client().get_trending_players(
        trend_type, lookback_hours, limit
    )


@st.cache_data(ttl=5, show_spinner=False)
def get_winners_bracket(league_id: str) -> BracketContainer:
    return get_sleeper_client().get_winners_bracket(league_id)


@st.cache_data(ttl=5, show_spinner=False)
def get_losers_bracket(league_id: str) -> BracketContainer:
    return get_sleeper_client().get_losers_bracket(league_id)


# Avatar IDs identify CDN objects, so their binary content can be retained longer.
@st.cache_data(ttl=86400, max_entries=256, show_spinner=False)
def get_avatar(avatar_id: str) -> bytes | None:
    return get_sleeper_client().get_avatar(avatar_id)


# Decode the large player file once per file version instead of on every rerun.
@st.cache_data(show_spinner=False)
def _load_nfl_players(
    path: str, modified_at_ns: int
) -> dict[str, dict[str, Any]]:
    del modified_at_ns
    with Path(path).open(encoding="utf-8") as player_file:
        data = json.load(player_file)
    return data if isinstance(data, dict) else {}


def get_nfl_players() -> dict[str, dict[str, Any]]:
    if not NFL_PLAYERS_PATH.exists():
        return {}
    return _load_nfl_players(
        str(NFL_PLAYERS_PATH),
        NFL_PLAYERS_PATH.stat().st_mtime_ns,
    )


# Clear related cache entries when a user explicitly requests fresh league data.
def clear_league_data(league_id: str) -> None:
    get_league.clear(league_id)
    get_league_users.clear(league_id)
    get_rosters.clear(league_id)


def clear_matchup_data(
    league_id: str,
    week: int,
    season: str,
    season_type: str,
) -> None:
    clear_league_data(league_id)
    get_weekly_matchups.clear(league_id, week)
    get_player_stats.clear(season, season_type, week)


def clear_ranking_data(league_id: str) -> None:
    clear_league_data(league_id)
    get_winners_bracket.clear(league_id)
    get_losers_bracket.clear(league_id)


def clear_league_list(user_id: str, season: str, sport: str = "nfl") -> None:
    get_leagues.clear(user_id, season, sport)


def clear_player_data(
    league_id: str,
    season: str,
    season_type: str,
    week: int | None,
) -> None:
    get_league.clear(league_id)
    get_rosters.clear(league_id)
    get_player_stats.clear(season, season_type, week)
