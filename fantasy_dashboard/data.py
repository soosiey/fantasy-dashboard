import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests
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
from fantasy_dashboard.paths import (
    ESPN_PROJECTIONS_CACHE_DIR,
    MANUAL_REFRESH_STATE_PATH,
    NFL_PLAYERS_PATH,
    WEEKLY_STATS_CACHE_DIR,
)

PLAYER_CATALOG_MAX_AGE = timedelta(days=1)
CURRENT_PROJECTION_CACHE_MAX_AGE = timedelta(hours=6)
LIVE_PROJECTION_CACHE_MAX_AGE = timedelta(hours=1)
PREGAME_ACTUAL_CACHE_MAX_AGE = timedelta(days=1)
LIVE_ACTUAL_CACHE_MAX_AGE = timedelta(minutes=1)
CORRECTION_WINDOW = timedelta(days=3)
MANUAL_REFRESH_COOLDOWN = timedelta(hours=6)
LIVE_GAME_STATUSES = {"in_progress", "in-progress", "live"}
COMPLETE_GAME_STATUSES = {"complete", "completed", "final", "post_game"}


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


def _stats_cache_path(
    provider: str,
    season: str,
    season_type: str,
    week: int | None,
) -> Path:
    filename = "season.json" if week is None else f"week_{week}.json"
    return WEEKLY_STATS_CACHE_DIR / provider / str(season) / season_type / filename


def _player_log_cache_path(
    player_id: str,
    season: str,
    season_type: str,
) -> Path:
    return (
        WEEKLY_STATS_CACHE_DIR
        / "sleeper_player_logs"
        / str(season)
        / season_type
        / f"{player_id}.json"
    )


def _is_cache_stale(path: Path, max_age: timedelta) -> bool:
    if not path.exists():
        return True
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return datetime.now(timezone.utc) - modified_at >= max_age


def _write_json_cache(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(value, temporary_file, separators=(",", ":"))
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@st.cache_data(max_entries=256, show_spinner=False)
def _read_json_cache(path: str, modified_at_ns: int) -> dict[str, Any]:
    del modified_at_ns
    with Path(path).open(encoding="utf-8") as cache_file:
        value = json.load(cache_file)
    if not isinstance(value, dict):
        raise TypeError(f"Cached data at {path} must be a JSON object.")
    return value


def _load_json_cache(path: Path) -> dict[str, Any]:
    return _read_json_cache(str(path), path.stat().st_mtime_ns)


def _cache_updated_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def get_manual_refresh_cooldown_remaining(
    *,
    now: datetime | None = None,
) -> timedelta:
    if not MANUAL_REFRESH_STATE_PATH.exists():
        return timedelta(0)
    try:
        state = _load_json_cache(MANUAL_REFRESH_STATE_PATH)
        refreshed_at = datetime.fromisoformat(str(state["refreshed_at"]))
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return timedelta(0)
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
    elapsed = (now or datetime.now(timezone.utc)) - refreshed_at
    return max(MANUAL_REFRESH_COOLDOWN - elapsed, timedelta(0))


def record_manual_refresh(*, refreshed_at: datetime | None = None) -> None:
    timestamp = refreshed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    _write_json_cache(
        MANUAL_REFRESH_STATE_PATH,
        {"refreshed_at": timestamp.astimezone(timezone.utc).isoformat()},
    )
    _read_json_cache.clear()


def _correction_deadline(games: list[dict[str, Any]]) -> datetime | None:
    statuses = {
        str(game.get("status") or "").casefold()
        for game in games
        if isinstance(game, dict)
    }
    if not statuses or not statuses.issubset(COMPLETE_GAME_STATUSES):
        return None

    game_dates: list[datetime] = []
    for game in games:
        try:
            game_date = datetime.fromisoformat(str(game.get("date") or ""))
        except ValueError:
            continue
        game_dates.append(game_date.replace(tzinfo=timezone.utc))
    if not game_dates:
        return None
    return max(game_dates) + CORRECTION_WINDOW


def _actual_cache_needs_refresh(
    path: Path,
    games: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> bool:
    if not path.exists():
        return True

    checked_at = now or datetime.now(timezone.utc)
    correction_deadline = _correction_deadline(games)
    if correction_deadline is not None:
        if checked_at >= correction_deadline:
            # Refresh exactly once after the correction window, then freeze.
            return _cache_updated_at(path) < correction_deadline
        # Keep the final in-game result untouched while corrections accumulate.
        return False

    statuses = {
        str(game.get("status") or "").casefold()
        for game in games
        if isinstance(game, dict)
    }
    max_age = (
        LIVE_ACTUAL_CACHE_MAX_AGE
        if statuses.intersection(LIVE_GAME_STATUSES)
        else PREGAME_ACTUAL_CACHE_MAX_AGE
    )
    return checked_at - _cache_updated_at(path) >= max_age


def _projection_cache_max_age(games: list[dict[str, Any]]) -> timedelta:
    statuses = {
        str(game.get("status") or "").casefold()
        for game in games
        if isinstance(game, dict)
    }
    if statuses.intersection(LIVE_GAME_STATUSES):
        return LIVE_PROJECTION_CACHE_MAX_AGE
    return CURRENT_PROJECTION_CACHE_MAX_AGE


# Keep this client ephemeral. Retaining it across Streamlit hot reloads can retain
# references to an older generation of the model classes imported by its module;
# returning one of those instances from cache_data then fails during pickling.
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
    if str(season) != str(state["season"]) or state.get("season_type") == "pre":
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
        weekly_transactions = get_sleeper_client().get_transactions(league_id, week)
        for transaction in weekly_transactions.transactions:
            transactions_by_id[transaction.transaction_id] = transaction
    transactions = TransactionContainer.from_models(list(transactions_by_id.values()))
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


def get_player_stats(
    season: str,
    season_type: str = "regular",
    week: int | None = None,
) -> dict[str, dict]:
    _clear_data_update("player_stats", season, season_type, week)
    cache_path = _stats_cache_path("sleeper", season, season_type, week)
    if not cache_path.exists():
        refresh_player_stats_cache(season, season_type, week)
    stats = _load_json_cache(cache_path)
    _record_data_update(
        "Sleeper",
        "player_stats",
        season,
        season_type,
        week,
        updated_at=_cache_updated_at(cache_path),
    )
    return {
        str(player_id): player_stats
        for player_id, player_stats in stats.items()
        if isinstance(player_stats, dict)
    }


def refresh_player_stats_cache(
    season: str,
    season_type: str = "regular",
    week: int | None = None,
) -> dict[str, dict]:
    stats = get_sleeper_client().get_player_stats(season, season_type, week)
    cache_path = _stats_cache_path("sleeper", season, season_type, week)
    _write_json_cache(cache_path, stats)
    _read_json_cache.clear()
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


def get_player_weekly_stats(
    player_id: str,
    season: str,
    season_type: str = "regular",
) -> dict[int, dict]:
    _clear_data_update("player_weekly_stats", player_id, season, season_type)
    cache_path = _player_log_cache_path(player_id, season, season_type)
    if not cache_path.exists():
        player_log = get_sleeper_client().get_player_weekly_stats(
            player_id,
            season,
            season_type,
        )
        _write_json_cache(
            cache_path,
            {str(week): record for week, record in player_log.items()},
        )
        _read_json_cache.clear()

    cached_log = _load_json_cache(cache_path)
    stats = {
        int(week): record
        for week, record in cached_log.items()
        if str(week).isdigit() and isinstance(record, dict)
    }

    # Shared bulk week files are authoritative for stat values after a refresh;
    # retain the player endpoint's opponent and home/away context around them.
    bulk_cache_folder = _stats_cache_path(
        "sleeper",
        season,
        season_type,
        1,
    ).parent
    latest_update = _cache_updated_at(cache_path)
    for week_path in bulk_cache_folder.glob("week_*.json"):
        try:
            week = int(week_path.stem.removeprefix("week_"))
        except ValueError:
            continue
        weekly_player_stats = _load_json_cache(week_path).get(str(player_id))
        if not isinstance(weekly_player_stats, dict):
            continue
        record = dict(stats.get(week, {}))
        record["week"] = week
        record["stats"] = weekly_player_stats
        stats[week] = record
        latest_update = max(latest_update, _cache_updated_at(week_path))

    _record_data_update(
        "Sleeper",
        "player_weekly_stats",
        player_id,
        season,
        season_type,
        updated_at=latest_update,
    )
    return stats


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def get_trending_players(
    trend_type: str,
    lookback_hours: int = 48,
    limit: int = 25,
) -> list[dict[str, int | str]]:
    _clear_data_update("trending_players", trend_type, lookback_hours, limit)
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


# Cache normalized ESPN projections by week as well as retaining the raw ESPN file.
def get_projected_player_stats(
    season: str,
    week: int | None,
) -> dict[str, dict[str, float]]:
    _clear_data_update("projected_player_stats", season, week)
    normalized_path = _stats_cache_path("espn", season, "regular", week)
    raw_cache_path = ESPN_PROJECTIONS_CACHE_DIR / f"{season}.json"
    normalized_is_older_than_raw = (
        normalized_path.exists()
        and raw_cache_path.exists()
        and normalized_path.stat().st_mtime_ns < raw_cache_path.stat().st_mtime_ns
    )
    if not normalized_path.exists() or normalized_is_older_than_raw:
        refresh_projected_player_stats_cache(season, week)
    stats = _load_json_cache(normalized_path)
    provider_cache_path = raw_cache_path if raw_cache_path.exists() else normalized_path
    _record_data_update(
        "ESPN",
        "projected_player_stats",
        season,
        week,
        updated_at=_cache_updated_at(provider_cache_path),
    )
    return {
        str(player_id): {
            str(stat_name): float(stat_value)
            for stat_name, stat_value in player_stats.items()
            if isinstance(stat_value, (int, float))
        }
        for player_id, player_stats in stats.items()
        if isinstance(player_stats, dict)
    }


def refresh_projected_player_stats_cache(
    season: str,
    week: int | None,
    *,
    force_provider: bool = False,
    raw_cache_max_age: timedelta = CURRENT_PROJECTION_CACHE_MAX_AGE,
) -> dict[str, dict[str, float]]:
    raw_cache_path = ESPN_PROJECTIONS_CACHE_DIR / f"{season}.json"
    projection_data = EspnClient().get_nfl_projections(
        season,
        raw_cache_path,
        max_age=timedelta(0) if force_provider else raw_cache_max_age,
    )
    stats = map_projections_to_sleeper(
        projection_data,
        get_nfl_players(),
        season,
        week,
    )
    normalized_path = _stats_cache_path("espn", season, "regular", week)
    _write_json_cache(normalized_path, stats)
    _read_json_cache.clear()
    return stats


def refresh_current_week_input_data(*, force: bool = False) -> tuple[str, str, int]:
    if force:
        get_nfl_state.clear()
    nfl_state = get_nfl_state()
    season = str(nfl_state["season"])
    season_type = str(nfl_state.get("season_type") or "regular")
    week = min(max(int(nfl_state.get("display_week") or nfl_state["week"]), 1), 18)
    try:
        schedule = get_nfl_schedule(season, season_type)
    except (OSError, TypeError, ValueError, requests.RequestException):
        schedule = []
    games_by_week: dict[int, list[dict[str, Any]]] = {
        schedule_week: [] for schedule_week in range(1, 19)
    }
    for game in schedule:
        try:
            schedule_week = int(game.get("week") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if schedule_week in games_by_week and isinstance(game, dict):
            games_by_week[schedule_week].append(game)
    current_games = games_by_week[week]
    checked_at = datetime.now(timezone.utc)

    actual_paths = [
        _stats_cache_path("sleeper", season, season_type, week),
        _stats_cache_path("sleeper", season, season_type, None),
    ]
    for cache_path, cache_week in zip(actual_paths, (week, None)):
        if force or _actual_cache_needs_refresh(
            cache_path,
            current_games,
            now=checked_at,
        ):
            refresh_player_stats_cache(season, season_type, cache_week)

    # Finalize any previously cached week after its correction window. Missing
    # historical weeks remain lazy and are fetched only when a page requests one.
    actual_cache_folder = actual_paths[0].parent
    for week_path in actual_cache_folder.glob("week_*.json"):
        try:
            cached_week = int(week_path.stem.removeprefix("week_"))
        except ValueError:
            continue
        cached_games = games_by_week.get(cached_week, [])
        if (
            cached_week != week
            and _correction_deadline(cached_games) is not None
            and _actual_cache_needs_refresh(
                week_path,
                cached_games,
                now=checked_at,
            )
        ):
            refresh_player_stats_cache(season, season_type, cached_week)

    projection_paths = [
        _stats_cache_path("espn", season, "regular", week),
        _stats_cache_path("espn", season, "regular", None),
    ]
    projection_max_age = _projection_cache_max_age(current_games)
    # A forced refresh belongs only to actual stats. Projection refreshes follow
    # their own daily/live schedule and are never forced by a UI control.
    if not force and any(
        _is_cache_stale(path, projection_max_age) for path in projection_paths
    ):
        for projection_week in (week, None):
            refresh_projected_player_stats_cache(
                season,
                projection_week,
                raw_cache_max_age=projection_max_age,
            )

    return season, season_type, week


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
    _stats_cache_path("sleeper", season, season_type, week).unlink(missing_ok=True)
    _read_json_cache.clear()
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
    _stats_cache_path("sleeper", season, season_type, week).unlink(missing_ok=True)
    _read_json_cache.clear()


def clear_projected_player_data(season: str, week: int | None) -> None:
    _stats_cache_path("espn", season, "regular", week).unlink(missing_ok=True)
    _read_json_cache.clear()
