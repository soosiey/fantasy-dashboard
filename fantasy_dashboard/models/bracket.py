from dataclasses import dataclass
from typing import Any


# Identify whether a future bracket slot comes from a prior winner or loser.
@dataclass(frozen=True, slots=True)
class BracketSource:
    outcome: str
    matchup_id: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BracketSource":
        if "w" in data:
            return cls(outcome="winner", matchup_id=int(data["w"]))
        return cls(outcome="loser", matchup_id=int(data["l"]))


# Represent one matchup returned by Sleeper's playoff bracket endpoint.
@dataclass(frozen=True, slots=True)
class BracketMatchup:
    round: int
    matchup_id: int
    team_1_roster_id: int | None
    team_2_roster_id: int | None
    winner_roster_id: int | None
    loser_roster_id: int | None
    team_1_from: BracketSource | None
    team_2_from: BracketSource | None
    placement: int | None

    @staticmethod
    def _parse_roster_id(value: Any) -> int | None:
        if value is None or isinstance(value, dict):
            return None
        return int(value)

    @staticmethod
    def _parse_source(value: Any) -> BracketSource | None:
        return BracketSource.from_json(value) if isinstance(value, dict) else None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BracketMatchup":
        team_1_source = data.get("t1_from") or (
            data.get("t1") if isinstance(data.get("t1"), dict) else None
        )
        team_2_source = data.get("t2_from") or (
            data.get("t2") if isinstance(data.get("t2"), dict) else None
        )
        return cls(
            round=int(data.get("r") or 0),
            matchup_id=int(data.get("m") or 0),
            team_1_roster_id=cls._parse_roster_id(data.get("t1")),
            team_2_roster_id=cls._parse_roster_id(data.get("t2")),
            winner_roster_id=cls._parse_roster_id(data.get("w")),
            loser_roster_id=cls._parse_roster_id(data.get("l")),
            team_1_from=cls._parse_source(team_1_source),
            team_2_from=cls._parse_source(team_2_source),
            placement=(int(data["p"]) if data.get("p") is not None else None),
        )


# Normalize every matchup in a winners-bracket response.
@dataclass(frozen=True, slots=True)
class BracketContainer:
    matchups: list[BracketMatchup]

    @classmethod
    def from_api(cls, data: list[dict[str, Any]]) -> "BracketContainer":
        return cls(matchups=[BracketMatchup.from_json(matchup) for matchup in data])
