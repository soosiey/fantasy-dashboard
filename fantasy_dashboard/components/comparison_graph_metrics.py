from typing import Any

from fantasy_dashboard.player_performance import (
    build_availability_statistics,
    build_consistency_statistics,
    build_core_performance_statistics,
    build_efficiency_statistics,
    build_opportunity_statistics,
    build_projection_accuracy_statistics,
    get_team_completed_weeks,
)

MAX_GRAPH_STATISTICS = 5


def get_comparison_player_name(
    player_id: str,
    players: dict[str, dict[str, Any]],
) -> str:
    player = players.get(player_id, {})
    name = (
        f"{player.get('first_name') or ''} "
        f"{player.get('last_name') or ''}"
    ).strip()
    position = str(player.get("position") or "—")
    return f"{name or player_id} ({position})"


def build_comparison_category_statistics(
    player_ids: list[str],
    players: dict[str, dict[str, Any]],
    actual_rows: dict[str, list[dict[str, Any]]],
    projected_rows: dict[str, list[dict[str, Any]]],
    schedule: list[dict[str, Any]],
    selected_weeks: list[int],
    selected_stat: str,
    positions_are_compatible: bool,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    categories = {
        "Core Performance": {
            player_id: build_core_performance_statistics(
                actual_rows[player_id], selected_stat
            )
            for player_id in player_ids
        },
        "Projection Accuracy": {
            player_id: build_projection_accuracy_statistics(
                actual_rows[player_id],
                projected_rows[player_id],
                selected_stat,
                hit_tolerance=3.0,
            )
            for player_id in player_ids
        },
        "Consistency": {
            player_id: build_consistency_statistics(
                actual_rows[player_id],
                projected_rows[player_id],
                selected_stat,
                consistency_band_percent=20.0,
                boom_bust_tolerance=3.0,
            )
            for player_id in player_ids
        },
    }
    if positions_are_compatible:
        categories["Opportunity"] = {
            player_id: build_opportunity_statistics(
                actual_rows[player_id],
                str(players[player_id].get("position") or ""),
            )
            for player_id in player_ids
        }
        categories["Efficiency"] = {
            player_id: build_efficiency_statistics(
                actual_rows[player_id],
                str(players[player_id].get("position") or ""),
            )
            for player_id in player_ids
        }
        selected_week_set = set(selected_weeks)
        categories["Availability"] = {}
        for player_id in player_ids:
            player = players[player_id]
            completed_weeks = [
                week
                for week in get_team_completed_weeks(
                    schedule,
                    str(player.get("team") or ""),
                )
                if week in selected_week_set
            ]
            categories["Availability"][player_id] = (
                build_availability_statistics(
                    actual_rows[player_id],
                    len(completed_weeks) if schedule else None,
                    str(player.get("injury_status") or ""),
                )
            )
    return categories


def get_comparison_metric_options(
    category_statistics: dict[str, dict[str, list[dict[str, Any]]]],
    selected_player_ids: list[str],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for category, statistics_by_player in category_statistics.items():
        for player_id in selected_player_ids:
            for metric in statistics_by_player.get(player_id, []):
                if metric["Key"] == "injury_status":
                    continue
                option_id = f"{category}:{metric['Key']}"
                if option_id in seen:
                    continue
                seen.add(option_id)
                options.append(
                    {
                        "id": option_id,
                        "category": category,
                        "key": str(metric["Key"]),
                        "label": f"{category} · {metric['Statistic']}",
                    }
                )
    return options
