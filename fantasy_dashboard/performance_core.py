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


