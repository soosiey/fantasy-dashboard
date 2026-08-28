import time
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import requests

from fantasy_dashboard.models.bracket import BracketContainer
from fantasy_dashboard.models.draft import DraftPickContainer
from fantasy_dashboard.models.league import (
    LeagueContainer,
    LeagueModel,
    RosterContainer,
)
from fantasy_dashboard.models.matchup import WeeklyMatchupContainer
from fantasy_dashboard.models.user import SleeperUser, UserContainer


# Wrap Sleeper HTTP endpoints and convert their responses into application models.
class SleeperClient:
    BASE_URL = "https://api.sleeper.app/v1"
    SCHEDULE_URL = "https://api.sleeper.app/schedule/nfl"
    PLAYER_STATS_URL = "https://api.sleeper.com/stats/nfl/player"
    AVATAR_URL = "https://sleepercdn.com/avatars/thumbs"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def refresh_nfl_players_cache(
        self,
        cache_path: str | Path,
        max_age: timedelta = timedelta(days=1),
    ) -> bool:
        cache_path = Path(cache_path)

        # Reuse a recent cache to avoid downloading the large player dataset.
        if cache_path.exists():
            age_seconds = time.time() - cache_path.stat().st_mtime
            if age_seconds <= max_age.total_seconds():
                print("No refresh for player file.")
                return False

        # Fetch and validate the complete NFL player payload.
        print("Refreshing player file.")
        response = requests.get(
            f"{self.BASE_URL}/players/nfl",
            timeout=self.timeout,
        )
        response.raise_for_status()

        players = response.json()
        if not isinstance(players, dict):
            raise TypeError("Sleeper's NFL players response must be a JSON object.")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None

        # Replace the cache atomically so interrupted writes cannot corrupt it.
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=cache_path.parent,
                prefix=f".{cache_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(response.content)
                temporary_path = Path(temporary_file.name)

            temporary_path.replace(cache_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return True

    # Fetch user and league-level resources from their corresponding endpoints.
    def get_user(self, username: str) -> SleeperUser | None:
        response = requests.get(
            f"{self.BASE_URL}/user/{username}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            return None

        return SleeperUser.from_api(data)

    # Read Sleeper's global NFL state to identify the active season and week.
    def get_nfl_state(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.BASE_URL}/state/nfl",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict) or not data.get("season"):
            raise TypeError("Sleeper's NFL state response must contain a season.")
        return data

    # Preserve unmodified Sleeper payloads for historical snapshot archives.
    def get_raw_api_data(self, endpoint: str) -> dict[str, Any] | list[Any]:
        response = requests.get(
            f"{self.BASE_URL}/{endpoint.lstrip('/')}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, (dict, list)):
            raise TypeError("Sleeper's API response must be an object or list.")
        return data

    def get_leagues(
        self, user_id: str, season: str, sport: str = "nfl"
    ) -> LeagueContainer:
        response = requests.get(
            f"{self.BASE_URL}/user/{user_id}/leagues/{sport}/{season}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            return None
        return LeagueContainer.from_api(data)

    def get_single_league(self, league_id: str) -> LeagueModel:
        response = requests.get(
            f"{self.BASE_URL}/league/{league_id}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            return None
        return LeagueModel.from_api(data)

    # Fetch the completed picks for one Sleeper draft, including auction costs.
    def get_draft_picks(self, draft_id: str) -> DraftPickContainer:
        response = requests.get(
            f"{self.BASE_URL}/draft/{draft_id}/picks",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise TypeError("Sleeper's draft picks response must be a list.")
        return DraftPickContainer.from_api(data)

    # Fetch binary avatar content separately from Sleeper's JSON API.
    def get_avatar(self, avatar_id: str) -> bytes:
        response = requests.get(
            f"{self.AVATAR_URL}/{avatar_id}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.content

        if not data:
            return None
        return data

    # Fetch the roster and member collections used to assemble league teams.
    def get_all_rosters(self, league_id: str) -> RosterContainer:
        response = requests.get(
            f"{self.BASE_URL}/league/{league_id}/rosters",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            return None
        return RosterContainer.from_api(data)

    # Fetch every roster's lineup and score for one league week.
    def get_matchups(self, league_id: str, week: int) -> WeeklyMatchupContainer:
        response = requests.get(
            f"{self.BASE_URL}/league/{league_id}/matchups/{week}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise TypeError("Sleeper's matchup response must be a list.")
        return WeeklyMatchupContainer.from_api(data)

    # Fetch raw NFL player statistics for a season or one selected week.
    def get_player_stats(
        self,
        season: str,
        season_type: str = "regular",
        week: int | None = None,
    ) -> dict[str, dict]:
        stats_url = f"{self.BASE_URL}/stats/nfl/{season_type}/{season}"
        if week is not None:
            stats_url = f"{stats_url}/{week}"

        response = requests.get(stats_url, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Sleeper's NFL stats response must be a JSON object.")
        return {
            str(player_id): stats
            for player_id, stats in data.items()
            if isinstance(stats, dict)
        }

    # Fetch the season schedule used to resolve each NFL team's weekly opponent.
    def get_nfl_schedule(
        self,
        season: str,
        season_type: str = "regular",
    ) -> list[dict]:
        response = requests.get(
            f"{self.SCHEDULE_URL}/{season_type}/{season}",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise TypeError("Sleeper's NFL schedule response must be a list.")
        return [game for game in data if isinstance(game, dict)]

    # Fetch one player's complete week-by-week game log in a single request.
    def get_player_weekly_stats(
        self,
        player_id: str,
        season: str,
        season_type: str = "regular",
    ) -> dict[int, dict]:
        response = requests.get(
            f"{self.PLAYER_STATS_URL}/{player_id}",
            params={
                "season": season,
                "season_type": season_type,
                "grouping": "week",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Sleeper's weekly player stats response must be an object.")
        return {
            int(week): record
            for week, record in data.items()
            if str(week).isdigit() and isinstance(record, dict)
        }

    # Fetch the most-added or most-dropped NFL players for a recent window.
    def get_trending_players(
        self,
        trend_type: str,
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> list[dict[str, int | str]]:
        if trend_type not in {"add", "drop"}:
            raise ValueError("Trend type must be either 'add' or 'drop'.")

        response = requests.get(
            f"{self.BASE_URL}/players/nfl/trending/{trend_type}",
            params={"lookback_hours": lookback_hours, "limit": limit},
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise TypeError("Sleeper's trending players response must be a list.")
        return [
            {"player_id": str(item["player_id"]), "count": int(item["count"])}
            for item in data
            if isinstance(item, dict)
            and item.get("player_id") is not None
            and item.get("count") is not None
        ]

    def get_all_users(self, league_id: str) -> UserContainer:
        response = requests.get(
            f"{self.BASE_URL}/league/{league_id}/users",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()

        if not data:
            return None
        return UserContainer.from_api(data)

    # Fetch the winners bracket used by the playoff rankings view.
    def get_winners_bracket(self, league_id: str) -> BracketContainer:
        response = requests.get(
            f"{self.BASE_URL}/league/{league_id}/winners_bracket",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise TypeError("Sleeper's winners bracket response must be a list.")
        return BracketContainer.from_api(data)

    # Fetch the losers bracket used by the playoff rankings view.
    def get_losers_bracket(self, league_id: str) -> BracketContainer:
        response = requests.get(
            f"{self.BASE_URL}/league/{league_id}/losers_bracket",
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise TypeError("Sleeper's losers bracket response must be a list.")
        return BracketContainer.from_api(data)
