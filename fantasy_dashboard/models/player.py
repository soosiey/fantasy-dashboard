from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlayerModel:
    first_name: str
    last_name: str
    number: int
    position: str
    depth_chart_order: int
    injury_status: str
    player_id: str
    rotoworld_id: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "first_name", str(self.first_name or ""))
        object.__setattr__(self, "last_name", str(self.last_name or ""))
        object.__setattr__(self, "number", int(self.number or 0))
        object.__setattr__(self, "position", str(self.position or ""))
        object.__setattr__(self, "depth_chart_order", int(self.depth_chart_order or 0))
        object.__setattr__(self, "injury_status", str(self.injury_status or ""))
        object.__setattr__(self, "player_id", str(self.player_id or ""))
        object.__setattr__(self, "rotoworld_id", int(self.rotoworld_id or 0))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PlayerModel":
        return cls(
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            number=data.get("number"),
            position=data.get("position"),
            depth_chart_order=data.get("depth_chart_order"),
            injury_status=data.get("injury_status"),
            player_id=data.get("player_id"),
            rotoworld_id=data.get("rotoworld_id"),
        )
