from typing import Any

from fantasy_dashboard.player_stats import build_player_stat_row


def build_actual_weekly_stat_rows(
    weekly_stats: dict[int, dict[str, Any]],
    scoring_settings: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep recorded zeroes while omitting weeks absent from the actual log."""
    rows: list[dict[str, Any]] = []
    for week in sorted(week for week in weekly_stats if 1 <= week <= 18):
        record = weekly_stats[week]
        stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
        row = build_player_stat_row(stats, scoring_settings, week)
        row["Opponent"] = str(record.get("opponent") or "—").strip().upper()
        rows.append(row)
    return rows


def build_week_axis_labels(
    schedule: list[dict[str, Any]],
    player_team: str,
    weekly_stats: dict[int, dict[str, Any]] | None = None,
) -> dict[int, str]:
    """Label each scheduled week with this player's opposing NFL team."""
    normalized_team = player_team.strip().upper()
    opponents_by_week: dict[int, str] = {}
    for game in schedule:
        try:
            week = int(game.get("week"))
        except (TypeError, ValueError):
            continue
        home = str(game.get("home") or "").strip().upper()
        away = str(game.get("away") or "").strip().upper()
        if normalized_team == home and away:
            opponents_by_week[week] = away
        elif normalized_team == away and home:
            opponents_by_week[week] = home

    for week, record in (weekly_stats or {}).items():
        opponent = str(record.get("opponent") or "").strip().upper()
        if opponent:
            opponents_by_week.setdefault(int(week), opponent)

    return {
        week: f"Week {week} · vs {opponent}"
        for week, opponent in opponents_by_week.items()
    }


def build_week_opponents(
    schedule: list[dict[str, Any]],
    player_team: str,
) -> dict[int, str]:
    """Return opponent abbreviations for each scheduled week."""
    axis_labels = build_week_axis_labels(schedule, player_team)
    return {week: label.rsplit("vs ", 1)[-1] for week, label in axis_labels.items()}
