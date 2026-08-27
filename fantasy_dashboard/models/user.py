from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleeperUser:
    user_id: str
    username: str
    display_name: str
    avatar_id: str

    def __post_init__(self):
        object.__setattr__(self, "user_id", str(self.user_id))
        object.__setattr__(self, "username", str(self.username))
        object.__setattr__(self, "display_name", str(self.display_name))
        object.__setattr__(self, "avatar_id", str(self.avatar_id))

    @classmethod
    def from_api(cls, data: dict[str, str]) -> "SleeperUser":
        return cls(
            user_id=data.get("user_id"),
            username=data.get("username"),
            display_name=data.get("display_name"),
            avatar_id=data.get("avatar"),
        )


@dataclass(frozen=True, slots=True)
class SleeperTeam:
    user_id: str
    display_name: str
    avatar_id: str
    team_name: str

    def __post_init__(self):
        object.__setattr__(self, "user_id", str(self.user_id))
        object.__setattr__(self, "display_name", str(self.display_name))
        object.__setattr__(self, "avatar_id", str(self.avatar_id))
        object.__setattr__(self, "team_name", str(self.team_name))

    @classmethod
    def from_json(cls, data: dict[str, str]) -> "SleeperTeam":
        return cls(
            user_id=data.get("user_id"),
            display_name=data.get("display_name"),
            avatar_id=data.get("avatar"),
            team_name=data.get("metadata").get("team_name"),
        )


@dataclass(frozen=True, slots=True)
class UserContainer:
    users: list

    def __post_init__(self):
        object.__setattr__(self, "users", [SleeperTeam.from_json(team) for team in self.users])

    @classmethod
    def from_api(cls, data: list[dict[str, str]]) -> "UserContainer":
        return cls(users=data)

