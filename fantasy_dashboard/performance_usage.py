"""Compatibility facade for opportunity and efficiency calculations."""

from fantasy_dashboard.performance_efficiency import (
    build_efficiency_statistics,
    build_efficiency_trend,
)
from fantasy_dashboard.performance_opportunity import (
    build_opportunity_statistics,
    build_opportunity_trend,
)

__all__ = [
    "build_efficiency_statistics",
    "build_efficiency_trend",
    "build_opportunity_statistics",
    "build_opportunity_trend",
]
