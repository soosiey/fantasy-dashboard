"""Public facade for player performance calculations grouped by metric family."""

from fantasy_dashboard.performance_availability import (
    build_availability_statistics,
    build_availability_trend,
    get_team_completed_weeks,
)
from fantasy_dashboard.performance_core import (
    build_core_performance_statistics,
    build_core_performance_trend,
    build_position_average_statistics,
    is_eligible_game,
)
from fantasy_dashboard.performance_prediction import (
    build_consistency_statistics,
    build_consistency_trend,
    build_metric_average_values,
    build_projection_accuracy_statistics,
    build_projection_accuracy_trend,
)
from fantasy_dashboard.performance_usage import (
    build_efficiency_statistics,
    build_efficiency_trend,
    build_opportunity_statistics,
    build_opportunity_trend,
)

__all__ = [
    "build_availability_statistics",
    "build_availability_trend",
    "build_consistency_statistics",
    "build_consistency_trend",
    "build_core_performance_statistics",
    "build_core_performance_trend",
    "build_efficiency_statistics",
    "build_efficiency_trend",
    "build_metric_average_values",
    "build_opportunity_statistics",
    "build_opportunity_trend",
    "build_position_average_statistics",
    "build_projection_accuracy_statistics",
    "build_projection_accuracy_trend",
    "get_team_completed_weeks",
    "is_eligible_game",
]
