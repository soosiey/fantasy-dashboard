import time
from datetime import timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

from fantasy_dashboard.models.league import (
    LeagueContainer,
    LeagueModel,
    RosterContainer,
)
from fantasy_dashboard.models.user import SleeperUser, UserContainer


class SleeperClient:
    BASE_URL = "https://api.sleeper.app/v1"
    AVATAR_URL = "https://sleepercdn.com/avatars/thumbs"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def refresh_nfl_players_cache(
        self,
        cache_path: str | Path,
        max_age: timedelta = timedelta(days=1),
    ) -> bool:
        cache_path = Path(cache_path)

        if cache_path.exists():
            age_seconds = time.time() - cache_path.stat().st_mtime
            if age_seconds <= max_age.total_seconds():
                print("No refresh for player file.")
                return False

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

    def get_leagues(self, user_id: str, season: str, sport: str = "nfl") -> LeagueContainer:
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
