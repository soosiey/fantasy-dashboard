import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from fantasy_dashboard.clients.espn import (
    EspnClient,
    map_projections_to_sleeper,
)
from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.models.bracket import BracketContainer
from fantasy_dashboard.models.draft import DraftPickContainer
from fantasy_dashboard.models.league import (
    LeagueContainer,
    LeagueModel,
    RosterContainer,
)
from fantasy_dashboard.models.matchup import WeeklyMatchupContainer
from fantasy_dashboard.models.transaction import TransactionContainer
from fantasy_dashboard.models.user import SleeperUser, UserContainer
from fantasy_dashboard.paths import ESPN_PROJECTIONS_CACHE_DIR, NFL_PLAYERS_PATH


# Track when cached provider data was actually fetched rather than page-rerun time.
@dataclass(frozen=True, slots=True)
class DataUpdate:
    provider: str
    updated_at: datetime


_DATA_UPDATES: dict[str, DataUpdate] = {}


def _data_update_key(resource: str, *identifiers: object) -> str:
    return ":".join([resource, *(str(identifier) for identifier in identifiers)])


def _record_data_update(
    provider: str,
    resource: str,
    *identifiers: object,
    updated_at: datetime | None = None,
) -> None:
    _DATA_UPDATES[_data_update_key(resource, *identifiers)] = DataUpdate(
        provider=provider,
        updated_at=updated_at or datetime.now(timezone.utc),
    )


def get_data_update(resource: str, *identifiers: object) -> DataUpdate | None:
    return _DATA_UPDATES.get(_data_update_key(resource, *identifiers))


def _clear_data_update(resource: str, *identifiers: object) -> None:
    _DATA_UPDATES.pop(_data_update_key(resource, *identifiers), None)


# Share the stateless Sleeper client across sessions and page reruns.
@st.cache_resource
def get_sleeper_client() -> SleeperClient:
    return SleeperClient()


# Cache account and league-list lookups that rarely change during a session.
@st.cache_data(ttl=3600, show_spinner=False)
def get_user(username: str) -> SleeperUser | None:
    _clear_data_update("user", username)
    user = get_sleeper_client().get_user(username)
    _record_data_update("Sleeper", "user", username)
    return user


@st.cache_data(ttl=3600, show_spinner=False)
def get_nfl_state() -> dict[str, Any]:
    _clear_data_update("nfl_state")
    state = get_sleeper_client().get_nfl_state()
    _record_data_update("Sleeper", "nfl_state")
    return state


def get_current_nfl_season() -> str:
    return str(get_nfl_state()["season"])


def get_current_nfl_week() -> int:
    state = get_nfl_state()
    week = int(state.get("display_week") or state.get("week"))
    return min(max(week, 1), 18)


def get_default_nfl_week(season: str) -> int:
    state = get_nfl_state()
    if (
        str(season) != str(state["season"])
        or state.get("season_type") == "pre"
    ):
        return 1
    week = int(state.get("display_week") or state.get("week"))
    return min(max(week, 1), 18)


@st.cache_data(ttl=1800, show_spinner=False)
def get_leagues(
    user_id: str, season: str, sport: str = "nfl"
) -> LeagueContainer | None:
    _clear_data_update("leagues", user_id, season, sport)
    leagues = get_sleeper_client().get_leagues(user_id, season, sport)
    _record_data_update("Sleeper", "leagues", user_id, season, sport)
    return leagues


# Cache stable league configuration longer than live roster and matchup data.
@st.cache_data(ttl=1800, show_spinner=False)
def get_league(league_id: str) -> LeagueModel | None:
    _clear_data_update("league", league_id)
    league = get_sleeper_client().get_single_league(league_id)
    _record_data_update("Sleeper", "league", league_id)
    return league


@st.cache_data(ttl=1800, show_spinner=False)
def get_draft_picks(draft_id: str) -> DraftPickContainer:
    _clear_data_update("draft_picks", draft_id)
    draft = get_sleeper_client().get_draft_picks(draft_id)
    _record_data_update("Sleeper", "draft_picks", draft_id)
    return draft


@st.cache_data(ttl=300, show_spinner=False)
def get_league_transactions(league_id: str) -> TransactionContainer:
    _clear_data_update("league_transactions", league_id)
    transactions_by_id = {}
    for week in range(1, 19):
        weekly_transactions = get_sleeper_client().get_transactions(
            league_id, week
        )
        for transaction in weekly_transactions.transactions:
            transactions_by_id[transaction.transaction_id] = transaction
    transactions = TransactionContainer.from_models(
        list(transactions_by_id.values())
    )
    _record_data_update("Sleeper", "league_transactions", league_id)
    return transactions


@st.cache_data(ttl=600, show_spinner=False)
def get_league_users(league_id: str) -> UserContainer | None:
    _clear_data_update("league_users", league_id)
    users = get_sleeper_client().get_all_users(league_id)
    _record_data_update("Sleeper", "league_users", league_id)
    return users


@st.cache_data(ttl=5, show_spinner=False)
def get_rosters(league_id: str) -> RosterContainer | None:
    _clear_data_update("rosters", league_id)
    rosters = get_sleeper_client().get_all_rosters(league_id)
    _record_data_update("Sleeper", "rosters", league_id)
    return rosters


# Keep live scores and playoff progression fresh while avoiding rerun requests.
@st.cache_data(ttl=5, max_entries=128, show_spinner=False)
def get_weekly_matchups(league_id: str, week: int) -> WeeklyMatchupContainer:
    _clear_data_update("weekly_matchups", league_id, week)
    matchups = get_sleeper_client().get_matchups(league_id, week)
    _record_data_update("Sleeper", "weekly_matchups", league_id, week)
    return matchups


@st.cache_data(ttl=5, max_entries=64, show_spinner=False)
def get_player_stats(
    season: str,
    season_type: str = "regular",
    week: int | None = None,
) -> dict[str, dict]:
    _clear_data_update("player_stats", season, season_type, week)
    stats = get_sleeper_client().get_player_stats(season, season_type, week)
    _record_data_update("Sleeper", "player_stats", season, season_type, week)
    return stats


@st.cache_data(ttl=30, max_entries=16, show_spinner=False)
def get_nfl_schedule(
    season: str,
    season_type: str = "regular",
) -> list[dict]:
    _clear_data_update("nfl_schedule", season, season_type)
    schedule = get_sleeper_client().get_nfl_schedule(season, season_type)
    _record_data_update("Sleeper", "nfl_schedule", season, season_type)
    return schedule


@st.cache_data(ttl=5, max_entries=256, show_spinner=False)
def get_player_weekly_stats(
    player_id: str,
    season: str,
    season_type: str = "regular",
) -> dict[int, dict]:
    _clear_data_update(
        "player_weekly_stats", player_id, season, season_type
    )
    stats = get_sleeper_client().get_player_weekly_stats(
        player_id, season, season_type
    )
    _record_data_update(
        "Sleeper", "player_weekly_stats", player_id, season, season_type
    )
    return stats


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def get_trending_players(
    trend_type: str,
    lookback_hours: int = 48,
    limit: int = 25,
) -> list[dict[str, int | str]]:
    _clear_data_update(
        "trending_players", trend_type, lookback_hours, limit
    )
    players = get_sleeper_client().get_trending_players(
        trend_type, lookback_hours, limit
    )
    _record_data_update(
        "Sleeper", "trending_players", trend_type, lookback_hours, limit
    )
    return players


@st.cache_data(ttl=5, show_spinner=False)
def get_winners_bracket(league_id: str) -> BracketContainer:
    _clear_data_update("winners_bracket", league_id)
    bracket = get_sleeper_client().get_winners_bracket(league_id)
    _record_data_update("Sleeper", "winners_bracket", league_id)
    return bracket


@st.cache_data(ttl=5, show_spinner=False)
def get_losers_bracket(league_id: str) -> BracketContainer:
    _clear_data_update("losers_bracket", league_id)
    bracket = get_sleeper_client().get_losers_bracket(league_id)
    _record_data_update("Sleeper", "losers_bracket", league_id)
    return bracket


# Avatar IDs identify CDN objects, so their binary content can be retained longer.
@st.cache_data(ttl=86400, max_entries=256, show_spinner=False)
def get_avatar(avatar_id: str) -> bytes | None:
    return get_sleeper_client().get_avatar(avatar_id)


# Decode the large player file once per file version instead of on every rerun.
@st.cache_data(show_spinner=False)
def _load_nfl_players(path: str, modified_at_ns: int) -> dict[str, dict[str, Any]]:
    del modified_at_ns
    with Path(path).open(encoding="utf-8") as player_file:
        data = json.load(player_file)
    return data if isinstance(data, dict) else {}


def get_nfl_players() -> dict[str, dict[str, Any]]:
    if not NFL_PLAYERS_PATH.exists():
        return {}
    players = _load_nfl_players(
        str(NFL_PLAYERS_PATH),
        NFL_PLAYERS_PATH.stat().st_mtime_ns,
    )
    _record_data_update(
        "Sleeper",
        "nfl_players",
        updated_at=datetime.fromtimestamp(
            NFL_PLAYERS_PATH.stat().st_mtime,
            timezone.utc,
        ),
    )
    return players


# Cache normalized ESPN projections in memory and on disk for one hour.
@st.cache_data(ttl=3600, max_entries=32, show_spinner=False)
def get_projected_player_stats(
    season: str,
    week: int | None,
) -> dict[str, dict[str, float]]:
    _clear_data_update("projected_player_stats", season, week)
    cache_path = ESPN_PROJECTIONS_CACHE_DIR / f"{season}.json"
    projection_data = EspnClient().get_nfl_projections(
        season,
        cache_path,
    )
    stats = map_projections_to_sleeper(
        projection_data,
        get_nfl_players(),
        season,
        week,
    )
    cache_updated_at = (
        datetime.fromtimestamp(cache_path.stat().st_mtime, timezone.utc)
        if cache_path.exists()
        else datetime.now(timezone.utc)
    )
    _record_data_update(
        "ESPN",
        "projected_player_stats",
        season,
        week,
        updated_at=cache_updated_at,
    )
    return stats


# Clear related cache entries when a user explicitly requests fresh league data.
def clear_league_data(league_id: str) -> None:
    get_league.clear(league_id)
    get_league_users.clear(league_id)
    get_rosters.clear(league_id)


def clear_draft_data(draft_id: str) -> None:
    get_draft_picks.clear(draft_id)


def clear_transaction_data(league_id: str) -> None:
    get_league_transactions.clear(league_id)


def clear_matchup_data(
    league_id: str,
    week: int,
    season: str,
    season_type: str,
) -> None:
    clear_league_data(league_id)
    get_weekly_matchups.clear(league_id, week)
    get_player_stats.clear(season, season_type, week)
    get_nfl_schedule.clear(season, season_type)


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


def clear_projected_player_data(season: str, week: int | None) -> None:
    get_projected_player_stats.clear(season, week)
