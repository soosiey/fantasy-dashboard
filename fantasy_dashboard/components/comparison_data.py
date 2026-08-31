from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from fantasy_dashboard import data
from fantasy_dashboard.player_performance import is_eligible_game
from fantasy_dashboard.player_stats import (
    build_player_stat_row,
    get_relevant_stat_fields,
)

FLEX_POSITIONS = {"RB", "WR", "TE"}
FULL_SEASON_WEEKS = tuple(range(1, 19))


def comparison_positions_are_compatible(positions: list[str]) -> bool:
    distinct_positions = {position.upper() for position in positions if position}
    return len(distinct_positions) <= 1 or distinct_positions <= FLEX_POSITIONS


@dataclass(slots=True)
class ComparisonDataContext:
    season: str
    weeks: tuple[int, ...]
    selected_player_ids: list[str]
    league_player_ids: list[str]
    actual_rows: dict[str, list[dict[str, Any]]]
    projected_rows: dict[str, list[dict[str, Any]]]
    schedule: list[dict[str, Any]]
    warnings: list[str]


class ComparisonDataProvider:
    def __init__(
        self,
        league_id: str,
        league: Any,
        players: dict[str, dict[str, Any]],
        comparison_player_ids: list[str],
    ) -> None:
        self.league_id = league_id
        self.league = league
        self.players = players
        self.selected_player_ids = [
            player_id
            for player_id in comparison_player_ids
            if player_id in players
        ]
        self.selected_positions = [
            str(players[player_id].get("position") or "")
            for player_id in self.selected_player_ids
        ]
        self.positions_are_compatible = comparison_positions_are_compatible(
            self.selected_positions
        )
        self._season_options: list[str] | None = None
        self.season_warning: str | None = None
        self._league_player_ids: list[str] | None = None
        self._roster_warning: str | None = None
        self._schedules: dict[str, tuple[list[dict[str, Any]], str | None]] = {}
        self._contexts: dict[
            tuple[str, tuple[int, ...]], ComparisonDataContext
        ] = {}

    def get_season_options(self) -> list[str]:
        if self._season_options is not None:
            return self._season_options
        try:
            current_season = int(data.get_current_nfl_season())
        except (requests.RequestException, KeyError, TypeError, ValueError):
            today = datetime.now(ZoneInfo("America/New_York")).date()
            current_season = today.year if today.month >= 3 else today.year - 1
            self.season_warning = (
                "The current NFL season could not be detected from Sleeper."
            )
        self._season_options = [
            str(current_season - offset) for offset in range(3)
        ]
        return self._season_options

    def get_stat_options(self) -> list[str]:
        if not self.positions_are_compatible:
            return ["Fantasy Points"]
        stat_options = list(
            dict.fromkeys(
                label
                for player_id in self.selected_player_ids
                for label, stat_key in get_relevant_stat_fields(
                    str(self.players[player_id].get("position") or "")
                )
                if stat_key != "gp"
            )
        )
        if "Fantasy Points" in stat_options:
            stat_options.remove("Fantasy Points")
        stat_options.insert(0, "Fantasy Points")
        return stat_options

    def player_name(self, player_id: str) -> str:
        player = self.players.get(player_id, {})
        name = (
            f"{player.get('first_name') or ''} "
            f"{player.get('last_name') or ''}"
        ).strip()
        position = str(player.get("position") or "—")
        return f"{name or player_id} ({position})"

    def _get_league_player_ids(self) -> list[str]:
        if self._league_player_ids is not None:
            return self._league_player_ids
        try:
            rosters = data.get_rosters(self.league_id)
            rostered_player_ids = {
                str(player_id)
                for roster in rosters.rosters
                for player_id in roster.players
                if player_id is not None and str(player_id) in self.players
            }
        except (requests.RequestException, TypeError, ValueError, AttributeError):
            rostered_player_ids = set(self.selected_player_ids)
            self._roster_warning = (
                "League rosters could not be loaded for the league averages."
            )
        self._league_player_ids = sorted(
            rostered_player_ids | set(self.selected_player_ids)
        )
        return self._league_player_ids

    def _get_schedule(self, season: str) -> tuple[list[dict[str, Any]], str | None]:
        if season in self._schedules:
            return self._schedules[season]
        try:
            result = (data.get_nfl_schedule(season, "regular"), None)
        except (requests.RequestException, TypeError, ValueError):
            result = ([], "The completed NFL schedule could not be loaded.")
        self._schedules[season] = result
        return result

    def _subset_context(
        self,
        full_context: ComparisonDataContext,
        weeks: tuple[int, ...],
    ) -> ComparisonDataContext:
        selected_week_set = set(weeks)
        return ComparisonDataContext(
            season=full_context.season,
            weeks=weeks,
            selected_player_ids=full_context.selected_player_ids,
            league_player_ids=full_context.league_player_ids,
            actual_rows={
                player_id: [
                    row
                    for row in rows
                    if int(row.get("Week") or 0) in selected_week_set
                ]
                for player_id, rows in full_context.actual_rows.items()
            },
            projected_rows={
                player_id: [
                    row
                    for row in rows
                    if int(row.get("Week") or 0) in selected_week_set
                ]
                for player_id, rows in full_context.projected_rows.items()
            },
            schedule=full_context.schedule,
            warnings=full_context.warnings,
        )

    def get_context(
        self,
        season: str,
        weeks: list[int] | tuple[int, ...],
    ) -> ComparisonDataContext:
        normalized_weeks = tuple(
            sorted({int(week) for week in weeks if 1 <= int(week) <= 18})
        )
        key = (str(season), normalized_weeks)
        if key in self._contexts:
            return self._contexts[key]

        full_key = (str(season), FULL_SEASON_WEEKS)
        if normalized_weeks != FULL_SEASON_WEEKS and full_key in self._contexts:
            context = self._subset_context(
                self._contexts[full_key], normalized_weeks
            )
            self._contexts[key] = context
            return context

        league_player_ids = self._get_league_player_ids()
        actual_rows = {player_id: [] for player_id in league_player_ids}
        projected_rows = {player_id: [] for player_id in league_player_ids}
        warnings = [warning for warning in (self._roster_warning,) if warning]
        try:
            for week in normalized_weeks:
                actual_stats = data.get_player_stats(
                    str(season), "regular", week
                )
                projected_stats = data.get_projected_player_stats(
                    str(season), week
                )
                for player_id in league_player_ids:
                    player_actual_stats = actual_stats.get(player_id, {})
                    if is_eligible_game({"stats": player_actual_stats}):
                        row = build_player_stat_row(
                            player_actual_stats,
                            self.league.scoring_settings,
                            week,
                            stats_available=True,
                        )
                        row["_Raw Stats"] = player_actual_stats
                        actual_rows[player_id].append(row)
                    player_projected_stats = projected_stats.get(player_id, {})
                    if player_projected_stats:
                        projected_rows[player_id].append(
                            build_player_stat_row(
                                player_projected_stats,
                                self.league.scoring_settings,
                                week,
                                stats_available=True,
                            )
                        )
        except (requests.RequestException, TypeError, ValueError):
            warnings.append("Some player statistics could not be loaded.")

        schedule, schedule_warning = self._get_schedule(str(season))
        if schedule_warning:
            warnings.append(schedule_warning)
        context = ComparisonDataContext(
            season=str(season),
            weeks=normalized_weeks,
            selected_player_ids=self.selected_player_ids,
            league_player_ids=league_player_ids,
            actual_rows=actual_rows,
            projected_rows=projected_rows,
            schedule=schedule,
            warnings=warnings,
        )
        self._contexts[key] = context
        return context
