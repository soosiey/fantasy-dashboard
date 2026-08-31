from numbers import Real
from typing import Any


def raw_stat_total(
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


def raw_stat_total_alias(
    weekly_rows: list[dict[str, Any]],
    *stat_names: str,
) -> float | None:
    for stat_name in stat_names:
        value = raw_stat_total(weekly_rows, stat_name)
        if value is not None:
            return value
    return None


def ratio(
    numerator: float | None,
    denominator: float | None,
    *,
    percentage: bool = False,
) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator
    return value * 100 if percentage else value
