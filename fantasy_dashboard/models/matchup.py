from dataclasses import dataclass, field
from typing import Any


# Represent one roster's score and lineup in a weekly Sleeper matchup.
@dataclass(frozen=True, slots=True)
class WeeklyMatchupModel:
    starters: list[str]
    players: list[str]
    roster_id: int
    matchup_id: int | None
    points: float
    custom_points: float | None
    players_points: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "starters", [str(player) for player in self.starters])
        object.__setattr__(self, "players", [str(player) for player in self.players])
        object.__setattr__(self, "roster_id", int(self.roster_id or 0))
        object.__setattr__(
            self,
            "matchup_id",
            int(self.matchup_id) if self.matchup_id is not None else None,
        )
        object.__setattr__(self, "points", float(self.points or 0))
        object.__setattr__(
            self,
            "custom_points",
            float(self.custom_points) if self.custom_points is not None else None,
        )
        object.__setattr__(
            self,
            "players_points",
            {
                str(player_id): float(points or 0)
                for player_id, points in self.players_points.items()
            },
        )

    @property
    def displayed_points(self) -> float:
        return self.custom_points if self.custom_points is not None else self.points

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "WeeklyMatchupModel":
        return cls(
            starters=data.get("starters") or [],
            players=data.get("players") or [],
            roster_id=data.get("roster_id"),
            matchup_id=data.get("matchup_id"),
            points=data.get("points"),
            custom_points=data.get("custom_points"),
            players_points=data.get("players_points") or {},
        )


# Normalize every roster entry returned for one league week.
@dataclass(frozen=True, slots=True)
class WeeklyMatchupContainer:
    matchups: list[WeeklyMatchupModel]

    @classmethod
    def from_api(cls, data: list[dict[str, Any]]) -> "WeeklyMatchupContainer":
        return cls(
            matchups=[WeeklyMatchupModel.from_json(matchup) for matchup in data]
        )
