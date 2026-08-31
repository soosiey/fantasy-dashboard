from typing import Any

from fantasy_dashboard.performance_common import (
    build_actual_statistics_trend,
    metric_row,
)
from fantasy_dashboard.performance_usage_common import ratio, raw_stat_total


def build_opportunity_statistics(
    weekly_rows: list[dict[str, Any]],
    position: str,
) -> list[dict[str, Any]]:
    """Summarize position-relevant opportunities from cached Sleeper fields."""
    games_played = len(weekly_rows)
    if games_played == 0:
        return []
    game_context = f"{games_played} eligible games"

    rush_attempts = raw_stat_total(weekly_rows, "rush_att")
    receptions = raw_stat_total(weekly_rows, "rec")
    targets = raw_stat_total(weekly_rows, "rec_tgt")
    pass_attempts = raw_stat_total(weekly_rows, "pass_att")
    offensive_snaps = raw_stat_total(weekly_rows, "off_snp")
    team_offensive_snaps = raw_stat_total(weekly_rows, "tm_off_snp")
    snap_share = ratio(offensive_snaps, team_offensive_snaps, percentage=True)
    unavailable = "Unavailable in the cached Sleeper weekly fields"

    if position == "QB":
        red_zone_values = (
            raw_stat_total(weekly_rows, "pass_rz_att"),
            raw_stat_total(weekly_rows, "rush_rz_att"),
        )
        red_zone_opportunities = (
            sum(value or 0 for value in red_zone_values)
            if any(value is not None for value in red_zone_values)
            else None
        )
        return [
            metric_row(
                "pass_attempts",
                "Pass attempts",
                pass_attempts,
                "Attempts",
                game_context,
            ),
            metric_row(
                "snap_share",
                "Snap share",
                snap_share,
                "%",
                game_context if snap_share is not None else unavailable,
            ),
            metric_row(
                "red_zone_opportunities",
                "Red-zone opportunities",
                red_zone_opportunities,
                "Attempts",
                (
                    "Pass attempts + rush attempts inside the 20"
                    if red_zone_opportunities is not None
                    else unavailable
                ),
                graphable=red_zone_opportunities is not None,
            ),
        ]

    if position in {"RB", "WR", "TE"}:
        touches = (
            (rush_attempts or 0) + (receptions or 0)
            if rush_attempts is not None or receptions is not None
            else None
        )
        red_zone_values = (
            raw_stat_total(weekly_rows, "rush_rz_att"),
            raw_stat_total(weekly_rows, "rec_rz_tgt"),
        )
        red_zone_opportunities = (
            sum(value or 0 for value in red_zone_values)
            if any(value is not None for value in red_zone_values)
            else None
        )
        return [
            metric_row("touches", "Touches", touches, "Touches", game_context),
            metric_row("targets", "Targets", targets, "Targets", game_context),
            metric_row(
                "snap_share",
                "Snap share",
                snap_share,
                "%",
                game_context if snap_share is not None else unavailable,
            ),
            metric_row(
                "red_zone_opportunities",
                "Red-zone opportunities",
                red_zone_opportunities,
                "Opportunities",
                (
                    "Carries + targets inside the 20"
                    if red_zone_opportunities is not None
                    else unavailable
                ),
                graphable=red_zone_opportunities is not None,
            ),
        ]

    if position == "K":
        return [
            metric_row(
                "field_goal_attempts",
                "Field-goal attempts",
                raw_stat_total(weekly_rows, "fga"),
                "Attempts",
                game_context,
            ),
            metric_row(
                "extra_point_attempts",
                "Extra-point attempts",
                raw_stat_total(weekly_rows, "xpa"),
                "Attempts",
                game_context,
            ),
        ]

    defensive_snaps = raw_stat_total(weekly_rows, "def_snp")
    team_defensive_snaps = raw_stat_total(weekly_rows, "tm_def_snp")
    defensive_snap_share = ratio(
        defensive_snaps,
        team_defensive_snaps,
        percentage=True,
    )
    return [
        metric_row(
            "snap_share",
            "Snap share",
            defensive_snap_share,
            "%",
            game_context if defensive_snap_share is not None else unavailable,
            graphable=defensive_snap_share is not None,
        )
    ]


def build_opportunity_trend(
    weekly_rows: list[dict[str, Any]],
    position: str,
    metric_key: str,
) -> list[dict[str, Any]]:
    return build_actual_statistics_trend(
        weekly_rows,
        metric_key,
        lambda rows: build_opportunity_statistics(rows, position),
    )
