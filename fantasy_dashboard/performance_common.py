from typing import Any


def metric_row(
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


def build_actual_statistics_trend(
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
