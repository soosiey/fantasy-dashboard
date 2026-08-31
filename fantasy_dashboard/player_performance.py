from math import isfinite
from numbers import Real
from typing import Any

import numpy as np


def is_eligible_game(record: dict[str, Any]) -> bool:
    """Treat an explicit zero-games record as a DNP, without dropping true zeroes."""
    stats = record.get("stats")
    if not isinstance(stats, dict) or not stats:
        return False

    games_played = stats.get("gp")
    return not isinstance(games_played, Real) or float(games_played) > 0


def build_core_performance_statistics(
    weekly_rows: list[dict[str, Any]],
    selected_stat: str,
) -> list[dict[str, Any]]:
    """Calculate the reference-defined core metrics for one selected weekly stat."""
    eligible_rows = [
        row
        for row in weekly_rows
        if isinstance(row.get(selected_stat), Real)
        and isfinite(float(row[selected_stat]))
    ]
    if not eligible_rows:
        return []

    values = np.asarray(
        [float(row[selected_stat]) for row in eligible_rows],
        dtype=float,
    )
    sample_size = len(values)
    season_average = float(np.mean(values))
    recent_sample_size = min(3, sample_size)
    recent_average = float(np.mean(values[-recent_sample_size:]))
    recent_difference = recent_average - season_average
    recent_percent_change = (
        (recent_difference / abs(season_average)) * 100 if season_average != 0 else None
    )
    best_index = int(np.argmax(values))
    worst_index = int(np.argmin(values))

    def week_context(row: dict[str, Any]) -> str:
        week = row.get("Week", "—")
        opponent = str(row.get("Opponent") or "—")
        return f"Week {week} · vs {opponent}"

    metrics = [
        (
            "average",
            "Average",
            "μ",
            float(np.mean(values)),
            f"{sample_size} eligible games",
        ),
        (
            "median",
            "Median",
            "Median",
            float(np.median(values)),
            f"{sample_size} eligible games",
        ),
        (
            "standard_deviation",
            "Standard deviation",
            "σ",
            float(np.std(values, ddof=0)),
            "Population standard deviation",
        ),
        (
            "floor_25",
            "Floor (25th percentile)",
            "Q25",
            float(np.quantile(values, 0.25)),
            "",
        ),
        (
            "ceiling_75",
            "Ceiling (75th percentile)",
            "Q75",
            float(np.quantile(values, 0.75)),
            "",
        ),
        (
            "ceiling_90",
            "Ceiling (90th percentile)",
            "Q90",
            float(np.quantile(values, 0.90)),
            "",
        ),
        (
            "season_total",
            "Season total",
            "Season total",
            float(np.sum(values)),
            f"{sample_size} eligible games",
        ),
        (
            "games_played",
            "Games played",
            "Games played",
            sample_size,
            "Eligible completed games",
        ),
        (
            "recent_average",
            f"Last-{recent_sample_size}-game average",
            f"Last-{recent_sample_size}-game average",
            recent_average,
            "Most recent eligible games",
        ),
        (
            "recent_difference",
            "Recent difference from season average",
            "Recent difference from season average",
            recent_difference,
            "",
        ),
        (
            "recent_percent_change",
            "Recent percent change",
            "Recent percent change",
            recent_percent_change,
            "",
        ),
        (
            "best_week",
            "Best week",
            "Best week",
            float(values[best_index]),
            week_context(eligible_rows[best_index]),
        ),
        (
            "worst_week",
            "Worst week",
            "Worst week",
            float(values[worst_index]),
            week_context(eligible_rows[worst_index]),
        ),
    ]
    statistics = [
        {
            "Key": metric_key,
            "Statistic": statistic,
            "Symbol": symbol,
            "Value": value,
            "Context": context,
        }
        for metric_key, statistic, symbol, value, context in metrics
    ]
    return statistics


def build_core_performance_trend(
    weekly_rows: list[dict[str, Any]],
    selected_stat: str,
    metric_key: str,
) -> list[dict[str, Any]]:
    """Recalculate one core metric after each successive eligible game."""
    trend_rows: list[dict[str, Any]] = []
    for end_index, weekly_row in enumerate(weekly_rows, start=1):
        metrics = build_core_performance_statistics(
            weekly_rows[:end_index],
            selected_stat,
        )
        selected_metric = next(
            (metric for metric in metrics if metric["Key"] == metric_key),
            None,
        )
        if selected_metric is None:
            continue

        week = weekly_row.get("Week", end_index)
        opponent = str(weekly_row.get("Opponent") or "—")
        trend_rows.append(
            {
                "Week": week,
                "Week Label": f"Week {week} · vs {opponent}",
                "Value": selected_metric["Value"],
            }
        )
    return trend_rows


def build_position_average_statistics(
    weekly_rows_by_player_id: dict[str, list[dict[str, Any]]],
    selected_stat: str,
) -> dict[str, float]:
    """Average each core metric across positional peers with eligible games."""
    values_by_metric_key: dict[str, list[float]] = {}
    for weekly_rows in weekly_rows_by_player_id.values():
        for metric in build_core_performance_statistics(weekly_rows, selected_stat):
            value = metric["Value"]
            if not isinstance(value, Real) or not isfinite(float(value)):
                continue
            values_by_metric_key.setdefault(str(metric["Key"]), []).append(float(value))

    return {
        metric_key: float(np.mean(metric_values))
        for metric_key, metric_values in values_by_metric_key.items()
        if metric_values
    }


def _matched_actual_and_predicted_values(
    actual_rows: list[dict[str, Any]],
    predicted_rows: list[dict[str, Any]],
    selected_stat: str,
) -> tuple[np.ndarray, np.ndarray]:
    actual_by_week = {
        row.get("Week"): float(row[selected_stat])
        for row in actual_rows
        if isinstance(row.get(selected_stat), Real)
        and isfinite(float(row[selected_stat]))
    }
    matched_values = [
        (actual_by_week[row.get("Week")], float(row[selected_stat]))
        for row in predicted_rows
        if row.get("Week") in actual_by_week
        and isinstance(row.get(selected_stat), Real)
        and isfinite(float(row[selected_stat]))
    ]
    if not matched_values:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    actual_values, predicted_values = zip(*matched_values)
    return (
        np.asarray(actual_values, dtype=float),
        np.asarray(predicted_values, dtype=float),
    )


def build_projection_accuracy_statistics(
    actual_rows: list[dict[str, Any]],
    predicted_rows: list[dict[str, Any]],
    selected_stat: str,
    *,
    hit_tolerance: float = 3.0,
) -> list[dict[str, Any]]:
    """Calculate accuracy for completed weeks with actual and predicted data."""
    actual_values, predicted_values = _matched_actual_and_predicted_values(
        actual_rows,
        predicted_rows,
        selected_stat,
    )
    sample_size = len(actual_values)
    if sample_size == 0:
        return []

    errors = actual_values - predicted_values
    absolute_errors = np.abs(errors)
    correlation = None
    if (
        sample_size >= 2
        and float(np.std(actual_values)) > 0
        and float(np.std(predicted_values)) > 0
    ):
        correlation = float(np.corrcoef(actual_values, predicted_values)[0, 1])

    matched_context = f"{sample_size} matched completed games"
    statistics = [
        {
            "Statistic": "Actual average",
            "Value": float(np.mean(actual_values)),
            "Unit": selected_stat,
            "Context": matched_context,
        },
        {
            "Statistic": "Predicted average",
            "Value": float(np.mean(predicted_values)),
            "Unit": selected_stat,
            "Context": matched_context,
        },
        {
            "Statistic": "MAE",
            "Value": float(np.mean(absolute_errors)),
            "Unit": selected_stat,
            "Context": matched_context,
        },
        {
            "Statistic": "Bias",
            "Value": float(np.mean(errors)),
            "Unit": selected_stat,
            "Context": "Positive means actual exceeded predicted",
        },
        {
            "Statistic": "RMSE",
            "Value": float(np.sqrt(np.mean(np.square(errors)))),
            "Unit": selected_stat,
            "Context": matched_context,
        },
        {
            "Statistic": "Hit rate",
            "Value": float(np.mean(absolute_errors <= hit_tolerance) * 100),
            "Unit": "%",
            "Context": f"Within ±{hit_tolerance:g} · {matched_context}",
        },
        {
            "Statistic": "r",
            "Value": correlation,
            "Unit": "Correlation",
            "Context": (
                matched_context
                if correlation is not None
                else "Unavailable: insufficient sample or zero variance"
            ),
        },
    ]
    metric_keys = {
        "Actual average": "actual_average",
        "Predicted average": "predicted_average",
        "MAE": "mae",
        "Bias": "bias",
        "RMSE": "rmse",
        "Hit rate": "hit_rate",
        "r": "correlation",
    }
    return [{"Key": metric_keys[str(row["Statistic"])], **row} for row in statistics]


def build_consistency_statistics(
    actual_rows: list[dict[str, Any]],
    predicted_rows: list[dict[str, Any]],
    selected_stat: str,
    *,
    consistency_band_percent: float = 20.0,
    boom_bust_tolerance: float = 3.0,
) -> list[dict[str, Any]]:
    """Calculate consistency, projection-relative reliability, and season trend."""
    actual_values = np.asarray(
        [
            float(row[selected_stat])
            for row in actual_rows
            if isinstance(row.get(selected_stat), Real)
            and isfinite(float(row[selected_stat]))
        ],
        dtype=float,
    )
    sample_size = len(actual_values)
    if sample_size == 0:
        return []

    season_average = float(np.mean(actual_values))
    consistency_tolerance = abs(season_average) * consistency_band_percent / 100
    consistency_rate = float(
        np.mean(np.abs(actual_values - season_average) <= consistency_tolerance) * 100
    )
    matched_actual, matched_predicted = _matched_actual_and_predicted_values(
        actual_rows,
        predicted_rows,
        selected_stat,
    )
    matched_sample_size = len(matched_actual)
    boom_rate = (
        float(np.mean(matched_actual >= matched_predicted + boom_bust_tolerance) * 100)
        if matched_sample_size
        else None
    )
    bust_rate = (
        float(np.mean(matched_actual <= matched_predicted - boom_bust_tolerance) * 100)
        if matched_sample_size
        else None
    )
    rolling_average = float(np.mean(actual_values[-3:])) if sample_size >= 3 else None
    trend_slope = (
        float(np.polyfit(np.arange(1, sample_size + 1), actual_values, 1)[0])
        if sample_size >= 2
        else None
    )
    matched_context = f"{matched_sample_size} matched completed games"
    statistics = [
        {
            "Statistic": "Consistency rate",
            "Value": consistency_rate,
            "Unit": "%",
            "Context": (
                f"Within ±{consistency_band_percent:g}% of season average "
                f"(±{consistency_tolerance:.2f}) · {sample_size} games"
            ),
        },
        {
            "Statistic": "Boom rate",
            "Value": boom_rate,
            "Unit": "%",
            "Context": (
                f"Actual ≥ predicted + {boom_bust_tolerance:g} · {matched_context}"
            ),
        },
        {
            "Statistic": "Bust rate",
            "Value": bust_rate,
            "Unit": "%",
            "Context": (
                f"Actual ≤ predicted − {boom_bust_tolerance:g} · {matched_context}"
            ),
        },
        {
            "Statistic": "Rolling 3-game average",
            "Value": rolling_average,
            "Unit": selected_stat,
            "Context": (
                "Most recent 3 eligible games"
                if rolling_average is not None
                else "Unavailable: requires 3 eligible games"
            ),
        },
        {
            "Statistic": "Trend slope",
            "Value": trend_slope,
            "Unit": f"{selected_stat} per game",
            "Context": (
                f"Least-squares slope · {sample_size} eligible games"
                if trend_slope is not None
                else "Unavailable: requires 2 eligible games"
            ),
        },
    ]
    metric_keys = {
        "Consistency rate": "consistency_rate",
        "Boom rate": "boom_rate",
        "Bust rate": "bust_rate",
        "Rolling 3-game average": "rolling_average_3",
        "Trend slope": "trend_slope",
    }
    return [{"Key": metric_keys[str(row["Statistic"])], **row} for row in statistics]


def build_metric_average_values(
    statistics_by_player_id: dict[str, list[dict[str, Any]]],
) -> dict[str, float]:
    """Average keyed derived metrics across players with available values."""
    values_by_metric_key: dict[str, list[float]] = {}
    for statistics in statistics_by_player_id.values():
        for statistic in statistics:
            value = statistic.get("Value")
            if not isinstance(value, Real) or not isfinite(float(value)):
                continue
            values_by_metric_key.setdefault(str(statistic["Key"]), []).append(
                float(value)
            )
    return {
        metric_key: float(np.mean(metric_values))
        for metric_key, metric_values in values_by_metric_key.items()
        if metric_values
    }


def _build_metric_trend(
    actual_rows: list[dict[str, Any]],
    predicted_rows: list[dict[str, Any]],
    metric_key: str,
    statistic_builder: Any,
) -> list[dict[str, Any]]:
    trend_rows: list[dict[str, Any]] = []
    for end_index, actual_row in enumerate(actual_rows, start=1):
        actual_prefix = actual_rows[:end_index]
        completed_weeks = {row.get("Week") for row in actual_prefix}
        predicted_prefix = [
            row for row in predicted_rows if row.get("Week") in completed_weeks
        ]
        statistics = statistic_builder(actual_prefix, predicted_prefix)
        selected_metric = next(
            (metric for metric in statistics if metric["Key"] == metric_key),
            None,
        )
        if selected_metric is None:
            continue
        week = actual_row.get("Week", end_index)
        opponent = str(actual_row.get("Opponent") or "—")
        trend_rows.append(
            {
                "Week": week,
                "Week Label": f"Week {week} · vs {opponent}",
                "Value": selected_metric["Value"],
            }
        )
    return trend_rows


def build_projection_accuracy_trend(
    actual_rows: list[dict[str, Any]],
    predicted_rows: list[dict[str, Any]],
    selected_stat: str,
    metric_key: str,
    *,
    hit_tolerance: float = 3.0,
) -> list[dict[str, Any]]:
    return _build_metric_trend(
        actual_rows,
        predicted_rows,
        metric_key,
        lambda actual, predicted: build_projection_accuracy_statistics(
            actual,
            predicted,
            selected_stat,
            hit_tolerance=hit_tolerance,
        ),
    )


def build_consistency_trend(
    actual_rows: list[dict[str, Any]],
    predicted_rows: list[dict[str, Any]],
    selected_stat: str,
    metric_key: str,
    *,
    consistency_band_percent: float = 20.0,
    boom_bust_tolerance: float = 3.0,
) -> list[dict[str, Any]]:
    return _build_metric_trend(
        actual_rows,
        predicted_rows,
        metric_key,
        lambda actual, predicted: build_consistency_statistics(
            actual,
            predicted,
            selected_stat,
            consistency_band_percent=consistency_band_percent,
            boom_bust_tolerance=boom_bust_tolerance,
        ),
    )


def _raw_stat_total(
    weekly_rows: list[dict[str, Any]],
    *stat_names: str,
) -> float | None:
    raw_stats = [
        row.get("_Raw Stats")
        for row in weekly_rows
        if isinstance(row.get("_Raw Stats"), dict)
    ]
    if not any(stat_name in stats for stats in raw_stats for stat_name in stat_names):
        return None
    return float(
        sum(
            float(stats.get(stat_name) or 0)
            for stats in raw_stats
            for stat_name in stat_names
            if isinstance(stats.get(stat_name), Real)
        )
    )


def _raw_stat_total_alias(
    weekly_rows: list[dict[str, Any]],
    *stat_names: str,
) -> float | None:
    for stat_name in stat_names:
        value = _raw_stat_total(weekly_rows, stat_name)
        if value is not None:
            return value
    return None


def _ratio(
    numerator: float | None,
    denominator: float | None,
    *,
    percentage: bool = False,
) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator
    return value * 100 if percentage else value


def _metric_row(
    key: str,
    statistic: str,
    value: float | None,
    unit: str,
    context: str,
    *,
    graphable: bool | None = None,
) -> dict[str, Any]:
    return {
        "Key": key,
        "Statistic": statistic,
        "Value": value,
        "Unit": unit,
        "Context": context,
        "Graphable": value is not None if graphable is None else graphable,
    }


def build_opportunity_statistics(
    weekly_rows: list[dict[str, Any]],
    position: str,
) -> list[dict[str, Any]]:
    """Summarize position-relevant opportunities from cached Sleeper fields."""
    games_played = len(weekly_rows)
    if games_played == 0:
        return []
    game_context = f"{games_played} eligible games"

    rush_attempts = _raw_stat_total(weekly_rows, "rush_att")
    receptions = _raw_stat_total(weekly_rows, "rec")
    targets = _raw_stat_total(weekly_rows, "rec_tgt")
    pass_attempts = _raw_stat_total(weekly_rows, "pass_att")
    offensive_snaps = _raw_stat_total(weekly_rows, "off_snp")
    team_offensive_snaps = _raw_stat_total(weekly_rows, "tm_off_snp")
    snap_share = _ratio(offensive_snaps, team_offensive_snaps, percentage=True)
    unavailable = "Unavailable in the cached Sleeper weekly fields"

    if position == "QB":
        red_zone_values = (
            _raw_stat_total(weekly_rows, "pass_rz_att"),
            _raw_stat_total(weekly_rows, "rush_rz_att"),
        )
        red_zone_opportunities = (
            sum(value or 0 for value in red_zone_values)
            if any(value is not None for value in red_zone_values)
            else None
        )
        return [
            _metric_row(
                "pass_attempts",
                "Pass attempts",
                pass_attempts,
                "Attempts",
                game_context,
            ),
            _metric_row(
                "snap_share",
                "Snap share",
                snap_share,
                "%",
                game_context if snap_share is not None else unavailable,
            ),
            _metric_row(
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
            _raw_stat_total(weekly_rows, "rush_rz_att"),
            _raw_stat_total(weekly_rows, "rec_rz_tgt"),
        )
        red_zone_opportunities = (
            sum(value or 0 for value in red_zone_values)
            if any(value is not None for value in red_zone_values)
            else None
        )
        return [
            _metric_row("touches", "Touches", touches, "Touches", game_context),
            _metric_row("targets", "Targets", targets, "Targets", game_context),
            _metric_row(
                "snap_share",
                "Snap share",
                snap_share,
                "%",
                game_context if snap_share is not None else unavailable,
            ),
            _metric_row(
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
            _metric_row(
                "field_goal_attempts",
                "Field-goal attempts",
                _raw_stat_total(weekly_rows, "fga"),
                "Attempts",
                game_context,
            ),
            _metric_row(
                "extra_point_attempts",
                "Extra-point attempts",
                _raw_stat_total(weekly_rows, "xpa"),
                "Attempts",
                game_context,
            ),
        ]

    defensive_snaps = _raw_stat_total(weekly_rows, "def_snp")
    team_defensive_snaps = _raw_stat_total(weekly_rows, "tm_def_snp")
    defensive_snap_share = _ratio(
        defensive_snaps,
        team_defensive_snaps,
        percentage=True,
    )
    return [
        _metric_row(
            "snap_share",
            "Snap share",
            defensive_snap_share,
            "%",
            game_context if defensive_snap_share is not None else unavailable,
            graphable=defensive_snap_share is not None,
        )
    ]


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
    pass_attempts = _raw_stat_total(weekly_rows, "pass_att")
    completions = _raw_stat_total(weekly_rows, "pass_cmp")
    passing_yards = _raw_stat_total(weekly_rows, "pass_yd")
    passing_touchdowns = _raw_stat_total(weekly_rows, "pass_td")
    interceptions = _raw_stat_total(weekly_rows, "pass_int")
    carries = _raw_stat_total(weekly_rows, "rush_att")
    rushing_yards = _raw_stat_total(weekly_rows, "rush_yd")
    rushing_touchdowns = _raw_stat_total(weekly_rows, "rush_td")
    targets = _raw_stat_total(weekly_rows, "rec_tgt")
    receptions = _raw_stat_total(weekly_rows, "rec")
    receiving_yards = _raw_stat_total(weekly_rows, "rec_yd")
    receiving_touchdowns = _raw_stat_total(weekly_rows, "rec_td")
    unavailable = "Unavailable: required opportunity count is zero or missing"

    if position == "QB":
        return [
            _metric_row(
                "completion_rate",
                "Completion rate",
                _ratio(completions, pass_attempts, percentage=True),
                "%",
                f"{pass_attempts or 0:g} pass attempts",
            ),
            _metric_row(
                "yards_per_pass_attempt",
                "Yards per pass attempt",
                _ratio(passing_yards, pass_attempts),
                "Yards/attempt",
                f"{pass_attempts or 0:g} pass attempts",
            ),
            _metric_row(
                "passing_touchdown_rate",
                "Passing touchdown rate",
                _ratio(passing_touchdowns, pass_attempts, percentage=True),
                "%",
                f"{pass_attempts or 0:g} pass attempts",
            ),
            _metric_row(
                "interception_rate",
                "Interception rate",
                _ratio(interceptions, pass_attempts, percentage=True),
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
            _metric_row(
                "fantasy_points_per_touch",
                "Fantasy points per touch",
                _ratio(fantasy_points, touches),
                "Points/touch",
                f"{touches or 0:g} touches" if touches else unavailable,
            ),
            _metric_row(
                "fantasy_points_per_target",
                "Fantasy points per target",
                _ratio(fantasy_points, targets),
                "Points/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            _metric_row(
                "yards_per_carry",
                "Yards per carry",
                _ratio(rushing_yards, carries),
                "Yards/carry",
                f"{carries or 0:g} carries" if carries else unavailable,
            ),
            _metric_row(
                "catch_rate",
                "Catch rate",
                _ratio(receptions, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            _metric_row(
                "yards_per_target",
                "Yards per target",
                _ratio(receiving_yards, targets),
                "Yards/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            _metric_row(
                "rushing_touchdown_rate",
                "Rushing touchdown rate",
                _ratio(rushing_touchdowns, carries, percentage=True),
                "%",
                f"{carries or 0:g} carries" if carries else unavailable,
            ),
            _metric_row(
                "receiving_touchdown_rate",
                "Receiving touchdown rate",
                _ratio(receiving_touchdowns, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
        ]

    if position in {"WR", "TE"}:
        return [
            _metric_row(
                "fantasy_points_per_target",
                "Fantasy points per target",
                _ratio(fantasy_points, targets),
                "Points/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            _metric_row(
                "catch_rate",
                "Catch rate",
                _ratio(receptions, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            _metric_row(
                "yards_per_target",
                "Yards per target",
                _ratio(receiving_yards, targets),
                "Yards/target",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
            _metric_row(
                "receiving_touchdown_rate",
                "Receiving touchdown rate",
                _ratio(receiving_touchdowns, targets, percentage=True),
                "%",
                f"{targets or 0:g} targets" if targets else unavailable,
            ),
        ]

    if position == "K":
        field_goal_attempts = _raw_stat_total(weekly_rows, "fga")
        extra_point_attempts = _raw_stat_total(weekly_rows, "xpa")
        return [
            _metric_row(
                "field_goal_rate",
                "Field-goal rate",
                _ratio(
                    _raw_stat_total(weekly_rows, "fgm"),
                    field_goal_attempts,
                    percentage=True,
                ),
                "%",
                f"{field_goal_attempts or 0:g} attempts",
            ),
            _metric_row(
                "extra_point_rate",
                "Extra-point rate",
                _ratio(
                    _raw_stat_total(weekly_rows, "xpm"),
                    extra_point_attempts,
                    percentage=True,
                ),
                "%",
                f"{extra_point_attempts or 0:g} attempts",
            ),
        ]

    sacks = _raw_stat_total(weekly_rows, "sack")
    if position in {"DL", "LB", "DB"}:
        tackles = _raw_stat_total_alias(weekly_rows, "tkl", "idp_tkl")
        solo_tackles = _raw_stat_total_alias(
            weekly_rows,
            "tkl_solo",
            "idp_tkl_solo",
        )
        return [
            _metric_row(
                "tackles_per_game",
                "Tackles per game",
                _ratio(tackles, float(games_played)),
                "Tackles/game",
                f"{games_played} eligible games",
            ),
            _metric_row(
                "solo_tackles_per_game",
                "Solo tackles per game",
                _ratio(solo_tackles, float(games_played)),
                "Tackles/game",
                f"{games_played} eligible games",
            ),
            _metric_row(
                "sacks_per_game",
                "Sacks per game",
                _ratio(sacks, float(games_played)),
                "Sacks/game",
                f"{games_played} eligible games",
            ),
        ]

    defensive_interceptions = _raw_stat_total(weekly_rows, "int")
    fumble_recoveries = _raw_stat_total(weekly_rows, "fum_rec")
    points_allowed = _raw_stat_total(weekly_rows, "pts_allow")
    takeaways = (
        (defensive_interceptions or 0) + (fumble_recoveries or 0)
        if defensive_interceptions is not None or fumble_recoveries is not None
        else None
    )
    return [
        _metric_row(
            "sacks_per_game",
            "Sacks per game",
            _ratio(sacks, float(games_played)),
            "Sacks/game",
            f"{games_played} eligible games",
        ),
        _metric_row(
            "takeaways_per_game",
            "Takeaways per game",
            _ratio(takeaways, float(games_played)),
            "Takeaways/game",
            f"{games_played} eligible games",
        ),
        _metric_row(
            "points_allowed_per_game",
            "Points allowed per game",
            _ratio(points_allowed, float(games_played)),
            "Points/game",
            f"{games_played} eligible games",
        ),
    ]


def get_team_completed_weeks(
    schedule: list[dict[str, Any]],
    team: str,
) -> list[int]:
    """Return scheduled weeks whose game has a final status for one NFL team."""
    completed_statuses = {
        "post",
        "post_game",
        "complete",
        "completed",
        "final",
        "closed",
    }
    normalized_team = team.strip().upper()
    completed_weeks: set[int] = set()
    for game in schedule:
        home = str(game.get("home") or "").strip().upper()
        away = str(game.get("away") or "").strip().upper()
        status = str(game.get("status") or "").strip().casefold()
        if normalized_team not in {home, away} or status not in completed_statuses:
            continue
        try:
            completed_weeks.add(int(game.get("week")))
        except (TypeError, ValueError):
            continue
    return sorted(week for week in completed_weeks if 1 <= week <= 18)


def build_availability_statistics(
    weekly_rows: list[dict[str, Any]],
    team_completed_games: int | None,
    injury_status: str | None,
) -> list[dict[str, Any]]:
    """Calculate availability without treating bye weeks as missed games."""
    games_played = len(weekly_rows)
    games_missed = (
        max(team_completed_games - games_played, 0)
        if team_completed_games is not None
        else None
    )
    availability_rate = (
        games_played / team_completed_games * 100 if team_completed_games else None
    )
    schedule_context = (
        f"{team_completed_games} completed team games"
        if team_completed_games is not None
        else "Unavailable: completed team schedule could not be determined"
    )
    designation = injury_status.strip() if injury_status else "No designation"
    return [
        _metric_row(
            "games_played",
            "Games played",
            float(games_played),
            "Games",
            f"{games_played} eligible games",
        ),
        _metric_row(
            "games_missed",
            "Games missed",
            float(games_missed) if games_missed is not None else None,
            "Games",
            schedule_context,
            graphable=games_missed is not None,
        ),
        _metric_row(
            "availability_rate",
            "Availability rate",
            availability_rate,
            "%",
            schedule_context,
            graphable=availability_rate is not None,
        ),
        _metric_row(
            "injury_status",
            "Injury status",
            None,
            "Designation",
            f"Current Sleeper designation: {designation}",
            graphable=False,
        ),
    ]


def _build_actual_statistics_trend(
    weekly_rows: list[dict[str, Any]],
    metric_key: str,
    statistic_builder: Any,
) -> list[dict[str, Any]]:
    trend_rows: list[dict[str, Any]] = []
    for end_index, weekly_row in enumerate(weekly_rows, start=1):
        statistics = statistic_builder(weekly_rows[:end_index])
        selected_metric = next(
            (metric for metric in statistics if metric["Key"] == metric_key),
            None,
        )
        if selected_metric is None:
            continue
        week = weekly_row.get("Week", end_index)
        opponent = str(weekly_row.get("Opponent") or "—")
        trend_rows.append(
            {
                "Week": week,
                "Week Label": f"Week {week} · vs {opponent}",
                "Value": selected_metric["Value"],
            }
        )
    return trend_rows


def build_opportunity_trend(
    weekly_rows: list[dict[str, Any]],
    position: str,
    metric_key: str,
) -> list[dict[str, Any]]:
    return _build_actual_statistics_trend(
        weekly_rows,
        metric_key,
        lambda rows: build_opportunity_statistics(rows, position),
    )


def build_efficiency_trend(
    weekly_rows: list[dict[str, Any]],
    position: str,
    metric_key: str,
) -> list[dict[str, Any]]:
    return _build_actual_statistics_trend(
        weekly_rows,
        metric_key,
        lambda rows: build_efficiency_statistics(rows, position),
    )


def build_availability_trend(
    weekly_rows: list[dict[str, Any]],
    completed_team_weeks: list[int],
    injury_status: str | None,
    metric_key: str,
) -> list[dict[str, Any]]:
    rows_by_week = {int(row["Week"]): row for row in weekly_rows}
    trend_rows: list[dict[str, Any]] = []
    trend_weeks = completed_team_weeks or sorted(rows_by_week)
    for completed_game_count, week in enumerate(trend_weeks, start=1):
        player_rows = [row for row in weekly_rows if int(row.get("Week") or 0) <= week]
        statistics = build_availability_statistics(
            player_rows,
            completed_game_count,
            injury_status,
        )
        selected_metric = next(
            (metric for metric in statistics if metric["Key"] == metric_key),
            None,
        )
        if selected_metric is None:
            continue
        opponent = str(rows_by_week.get(week, {}).get("Opponent") or "—")
        trend_rows.append(
            {
                "Week": week,
                "Week Label": f"Week {week} · vs {opponent}",
                "Value": selected_metric["Value"],
            }
        )
    return trend_rows
