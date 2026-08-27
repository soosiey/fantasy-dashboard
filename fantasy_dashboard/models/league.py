from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Settings:
    waiver_budget: int
    playoff_teams: int
    num_teams: int
    playoff_start_week: int
    waiver_day: int
    trade_deadline: int
    reserves: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "waiver_budget", int(self.waiver_budget))
        object.__setattr__(self, "playoff_teams", int(self.playoff_teams))
        object.__setattr__(self, "num_teams", int(self.num_teams))
        object.__setattr__(self, "playoff_start_week", int(self.playoff_start_week))
        object.__setattr__(
            self,
            "waiver_day",
            {
                0: "Monday",
                1: "Tuesday",
                2: "Wednesday",
                3: "Thursday",
                4: "Friday",
                5: "Saturday",
                6: "Sunday",
            }[self.waiver_day],
        )
        object.__setattr__(self, "trade_deadline", int(self.trade_deadline))
        object.__setattr__(self, "reserves", int(self.reserves))


@dataclass(frozen=True, slots=True)
class LeagueModel:
    league_id: str
    rosters: int
    status: str
    sport: str
    settings: dict
    roster_positions: list
    name: str
    draft_id: str
    scoring_settings: dict
    bracket_id: str
    loser_bracket_id: str
    avatar_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "league_id", str(self.league_id))
        object.__setattr__(self, "rosters", int(self.rosters))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "sport", str(self.sport))
        object.__setattr__(
            self,
            "settings",
            (
                self.settings
                if isinstance(self.settings, Settings)
                else Settings(
                    waiver_budget=self.settings.get("waiver_budget"),
                    playoff_teams=self.settings.get("playoff_teams"),
                    num_teams=self.settings.get("num_teams"),
                    playoff_start_week=self.settings.get("playoff_week_start"),
                    waiver_day=self.settings.get("waiver_day_of_week"),
                    trade_deadline=self.settings.get("trade_deadline"),
                    reserves=self.settings.get("reserve_slots"),
                )
            ),
        )
        object.__setattr__(self, "roster_positions", list(self.roster_positions))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "draft_id", str(self.draft_id))
        object.__setattr__(
            self,
            "scoring_settings",
            {key: value for key, value in self.scoring_settings.items()},
        )
        object.__setattr__(self, "bracket_id", str(self.bracket_id))
        object.__setattr__(self, "loser_bracket_id", str(self.loser_bracket_id))
        object.__setattr__(self, "avatar_id", str(self.avatar_id))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "LeagueModel":
        return cls(
            league_id=data.get("league_id"),
            rosters=data.get("total_rosters"),
            status=data.get("status"),
            sport=data.get("sport"),
            settings=data.get("settings"),
            roster_positions=data.get("roster_positions"),
            name=data.get("name"),
            draft_id=data.get("draft_id"),
            scoring_settings=data.get("scoring_settings"),
            bracket_id=data.get("bracket_id"),
            loser_bracket_id=data.get("loser_bracket_id"),
            avatar_id=data.get("avatar"),
        )

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "LeagueModel":
        return cls(
            league_id=data.get("league_id"),
            rosters=data.get("total_rosters"),
            status=data.get("status"),
            sport=data.get("sport"),
            settings=data.get("settings"),
            roster_positions=data.get("roster_positions"),
            name=data.get("name"),
            draft_id=data.get("draft_id"),
            scoring_settings=data.get("scoring_settings"),
            bracket_id=data.get("bracket_id"),
            loser_bracket_id=data.get("loser_bracket_id"),
            avatar_id=data.get("avatar"),
        )


@dataclass(frozen=True, slots=True)
class LeagueContainer:
    leagues: list

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "leagues",
            [
                (
                    league
                    if isinstance(league, LeagueModel)
                    else LeagueModel.from_json(league)
                )
                for league in self.leagues
            ],
        )

    @classmethod
    def from_api(cls, data: list[dict[str, Any]]) -> "LeagueContainer":
        return cls(leagues=data)


@dataclass(frozen=True, slots=True)
class RosterModel:
    starters: list
    wins: int
    waiver: int
    budget_used: int
    moves: int
    ties: int
    losses: int
    points: float
    roster_id: int
    reserve: list
    players: list
    user_id: str
    league_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "starters", list(self.starters or []))
        object.__setattr__(self, "wins", int(self.wins))
        object.__setattr__(self, "waiver", int(self.waiver))
        object.__setattr__(self, "budget_used", int(self.budget_used))
        object.__setattr__(self, "moves", int(self.moves))
        object.__setattr__(self, "ties", int(self.ties))
        object.__setattr__(self, "losses", int(self.losses))
        object.__setattr__(self, "points", float(self.points))
        object.__setattr__(self, "roster_id", int(self.roster_id))
        object.__setattr__(self, "reserve", list(self.reserve or []))
        object.__setattr__(self, "players", list(self.players or []))
        object.__setattr__(self, "user_id", str(self.user_id))
        object.__setattr__(self, "league_id", str(self.league_id))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "RosterModel":
        settings = data.get("settings")
        return cls(
            starters=data.get("starters"),
            wins=settings.get("wins"),
            waiver=settings.get("waiver_position"),
            budget_used=settings.get("waiver_budget_used"),
            moves=settings.get("total_moves"),
            ties=settings.get("ties"),
            losses=settings.get("losses"),
            points=settings.get("fpts"),
            roster_id=data.get("roster_id"),
            reserve=data.get("reserve"),
            players=data.get("players"),
            user_id=data.get("owner_id"),
            league_id=data.get("league_id"),
        )


@dataclass(frozen=True, slots=True)
class RosterContainer:
    rosters: list

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rosters",
            [
                (
                    roster
                    if isinstance(roster, RosterModel)
                    else RosterModel.from_json(roster)
                )
                for roster in self.rosters
            ],
        )

    @classmethod
    def from_api(cls, data: list[dict[str, Any]]) -> "RosterContainer":
        return cls(rosters=data)
