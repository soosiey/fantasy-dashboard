from typing import Any

from fantasy_dashboard.performance_common import metric_row


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
        metric_row(
            "games_played",
            "Games played",
            float(games_played),
            "Games",
            f"{games_played} eligible games",
        ),
        metric_row(
            "games_missed",
            "Games missed",
            float(games_missed) if games_missed is not None else None,
            "Games",
            schedule_context,
            graphable=games_missed is not None,
        ),
        metric_row(
            "availability_rate",
            "Availability rate",
            availability_rate,
            "%",
            schedule_context,
            graphable=availability_rate is not None,
        ),
        metric_row(
            "injury_status",
            "Injury status",
            None,
            "Designation",
            f"Current Sleeper designation: {designation}",
            graphable=False,
        ),
    ]

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
