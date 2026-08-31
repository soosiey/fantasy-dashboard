from math import isfinite
from numbers import Real
from typing import Any

import numpy as np


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
