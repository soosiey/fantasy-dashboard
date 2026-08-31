from dataclasses import dataclass
from typing import Any


# Represent one completed Sleeper draft pick and its optional auction cost.
@dataclass(frozen=True, slots=True)
class DraftPickModel:
    pick_number: int
    player_id: str
    player_name: str
    amount: float | None
    picked_by: str = ""
    round_number: int = 0

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "DraftPickModel":
        metadata = data.get("metadata") or {}
        first_name = str(metadata.get("first_name") or "").strip()
        last_name = str(metadata.get("last_name") or "").strip()
        raw_amount = metadata.get("amount")

        try:
            amount = float(raw_amount) if raw_amount not in (None, "") else None
        except (TypeError, ValueError):
            amount = None

        return cls(
            pick_number=int(data.get("pick_no") or 0),
            player_id=str(data.get("player_id") or ""),
            player_name=" ".join(part for part in (first_name, last_name) if part),
            amount=amount,
            picked_by=str(data.get("picked_by") or ""),
            round_number=int(data.get("round") or 0),
        )

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "DraftPickModel":
        return cls.from_json(data)


# Normalize a draft-picks response and keep picks ordered chronologically.
@dataclass(frozen=True, slots=True)
class DraftPickContainer:
    picks: list[DraftPickModel]

    @classmethod
    def from_api(cls, data: list[dict[str, Any]]) -> "DraftPickContainer":
        picks = [
            DraftPickModel.from_api(pick) for pick in data if isinstance(pick, dict)
        ]
        return cls(picks=sorted(picks, key=lambda pick: pick.pick_number))
