from numbers import Real
from typing import Any

from fantasy_dashboard.performance_common import (
    build_actual_statistics_trend,
    metric_row,
)
from fantasy_dashboard.performance_usage_common import (
    ratio,
    raw_stat_total,
    raw_stat_total_alias,
)


def build_efficiency_statistics(
    weekly_rows: list[dict[str, Any]],
    position: str,
) -> list[dict[str, Any]]:
    """Calculate position-specific season efficiency with volume context."""
    games_played = len(weekly_rows)
    if games_played == 0:
        return []

    fantasy_points = float(
        sum(
            float(row.get("Fantasy Points") or 0)
            for row in weekly_rows
            if isinstance(row.get("Fantasy Points"), Real)
        )
    )
    pass_attempts = raw_stat_total(weekly_rows, "pass_att")
    completions = raw_stat_total(weekly_rows, "pass_cmp")
    passing_yards = raw_stat_total(weekly_rows, "pass_yd")
    passing_touchdowns = raw_stat_total(weekly_rows, "pass_td")
    interceptions = raw_stat_total(weekly_rows, "pass_int")
    carries = raw_stat_total(weekly_rows, "rush_att")
    rushing_yards = raw_stat_total(weekly_rows, "rush_yd")
    rushing_touchdowns = raw_stat_total(weekly_rows, "rush_td")
    targets = raw_stat_total(weekly_rows, "rec_tgt")
    receptions = raw_stat_total(weekly_rows, "rec")
    receiving_yards = raw_stat_total(weekly_rows, "rec_yd")
    receiving_touchdowns = raw_stat_total(weekly_rows, "rec_td")
    unavailable = "Unavailable: required opportunity count is zero or missing"

    if position == "QB":
        return [
            metric_row(
                "completion_rate",
                "Completion rate",
                ratio(completions, pass_attempts, percentage=True),
                "%",
                f"{pass_attempts or 0:g} pass attempts",
            ),
            metric_row(
                "yards_per_pass_attempt",
                "Yards per pass attempt",
                ratio(passing_yards, pass_attempts),
                "Yards/attempt",
                f"{pass_attempts or 0:g} pass attempts",
            ),
            metric_row(
                "passing_touchdown_rate",
                "Passing touchdown rate",
                ratio(passing_touchdowns, pass_attempts, percentage=True),
                "%",
                f"{pass_attempts or 0:g} pass attempts",
            ),
            metric_row(
                "interception_rate",
                "Interception rate",
                ratio(interceptions, pass_attempts, percentage=True),
                "%",
                f"{pass_attempts or 0:g} pass attempts",
            ),
        ]

    if position == "RB":
        touches = (
            (carries or 0) + (receptions or 0)
            if carries is not None or receptions is not None
            else None
        )
        return [
            metric_row(
                "fantasy_points_per_touch",
                "Fantasy points per touch",
                ratio(fantasy_points, touches),
                "Points/touch",
                f"{touches or 0:g} touches" if touches else unavailable,
            ),
            metric_row(
                "fantasy_points_per_target",
                "Fantasy points per target",
                ratio(fantasy_points, targets),
                "Points/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            metric_row(
                "yards_per_carry",
                "Yards per carry",
                ratio(rushing_yards, carries),
                "Yards/carry",
                f"{carries or 0:g} carries" if carries else unavailable,
            ),
            metric_row(
                "catch_rate",
                "Catch rate",
                ratio(receptions, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            metric_row(
                "yards_per_target",
                "Yards per target",
                ratio(receiving_yards, targets),
                "Yards/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            metric_row(
                "rushing_touchdown_rate",
                "Rushing touchdown rate",
                ratio(rushing_touchdowns, carries, percentage=True),
                "%",
                f"{carries or 0:g} carries" if carries else unavailable,
            ),
            metric_row(
                "receiving_touchdown_rate",
                "Receiving touchdown rate",
                ratio(receiving_touchdowns, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
        ]

    if position in {"WR", "TE"}:
        return [
            metric_row(
                "fantasy_points_per_target",
                "Fantasy points per target",
                ratio(fantasy_points, targets),
                "Points/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            metric_row(
                "catch_rate",
                "Catch rate",
                ratio(receptions, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            metric_row(
                "yards_per_target",
                "Yards per target",
                ratio(receiving_yards, targets),
                "Yards/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            metric_row(
                "receiving_touchdown_rate",
                "Receiving touchdown rate",
                ratio(receiving_touchdowns, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
        ]

    if position == "K":
        field_goal_attempts = raw_stat_total(weekly_rows, "fga")
        extra_point_attempts = raw_stat_total(weekly_rows, "xpa")
        return [
            metric_row(
                "field_goal_rate",
                "Field-goal rate",
                ratio(
                    raw_stat_total(weekly_rows, "fgm"),
                    field_goal_attempts,
                    percentage=True,
                ),
                "%",
                f"{field_goal_attempts or 0:g} attempts",
            ),
            metric_row(
                "extra_point_rate",
                "Extra-point rate",
                ratio(
                    raw_stat_total(weekly_rows, "xpm"),
                    extra_point_attempts,
                    percentage=True,
                ),
                "%",
                f"{extra_point_attempts or 0:g} attempts",
            ),
        ]

    sacks = raw_stat_total(weekly_rows, "sack")
    if position in {"DL", "LB", "DB"}:
        tackles = raw_stat_total_alias(weekly_rows, "tkl", "idp_tkl")
        solo_tackles = raw_stat_total_alias(
            weekly_rows,
            "tkl_solo",
            "idp_tkl_solo",
        )
        return [
            metric_row(
                "tackles_per_game",
                "Tackles per game",
                ratio(tackles, float(games_played)),
                "Tackles/game",
                f"{games_played} eligible games",
            ),
            metric_row(
                "solo_tackles_per_game",
                "Solo tackles per game",
                ratio(solo_tackles, float(games_played)),
                "Tackles/game",
                f"{games_played} eligible games",
            ),
            metric_row(
                "sacks_per_game",
                "Sacks per game",
                ratio(sacks, float(games_played)),
                "Sacks/game",
                f"{games_played} eligible games",
            ),
        ]

    defensive_interceptions = raw_stat_total(weekly_rows, "int")
    fumble_recoveries = raw_stat_total(weekly_rows, "fum_rec")
    points_allowed = raw_stat_total(weekly_rows, "pts_allow")
    takeaways = (
        (defensive_interceptions or 0) + (fumble_recoveries or 0)
        if defensive_interceptions is not None or fumble_recoveries is not None
        else None
    )
    return [
        metric_row(
            "sacks_per_game",
            "Sacks per game",
            ratio(sacks, float(games_played)),
            "Sacks/game",
            f"{games_played} eligible games",
        ),
        metric_row(
            "takeaways_per_game",
            "Takeaways per game",
            ratio(takeaways, float(games_played)),
            "Takeaways/game",
            f"{games_played} eligible games",
        ),
        metric_row(
            "points_allowed_per_game",
            "Points allowed per game",
            ratio(points_allowed, float(games_played)),
            "Points/game",
            f"{games_played} eligible games",
        ),
    ]


def build_efficiency_trend(
    weekly_rows: list[dict[str, Any]],
    position: str,
    metric_key: str,
) -> list[dict[str, Any]]:
    return build_actual_statistics_trend(
        weekly_rows,
        metric_key,
        lambda rows: build_efficiency_statistics(rows, position),
    )
