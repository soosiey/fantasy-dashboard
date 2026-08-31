from html import escape
from numbers import Real
from typing import Any

import streamlit as st

from fantasy_dashboard.player_stats import (
    calculate_fantasy_points,
    get_relevant_stat_fields,
    truncate_decimal,
)

LOWER_IS_BETTER = {"Pass INT", "Pts Allowed", "Yds Allowed"}


# Resolve Sleeper's broader fantasy position when the primary position is specific.
def _get_player_position(player: dict[str, Any]) -> str:
    fantasy_positions = player.get("fantasy_positions") or []
    return str(next(iter(fantasy_positions), player.get("position") or ""))


def _get_player_name(player_id: str | None, player: dict[str, Any]) -> str:
    name = (f"{player.get('first_name') or ''} {player.get('last_name') or ''}").strip()
    return name or player_id or "Empty"


# Render both players around centered stat labels in one mirrored table.
def _render_comparison_table(
    left_player_id: str | None,
    left_player: dict[str, Any],
    left_stats: dict[str, Any],
    right_player_id: str | None,
    right_player: dict[str, Any],
    right_stats: dict[str, Any],
    scoring_settings: dict[str, Any],
    stat_fields: list[tuple[str, str | None]],
    *,
    left_stats_available: bool | None = None,
    right_stats_available: bool | None = None,
) -> str:
    if left_stats_available is None:
        left_stats_available = bool(left_stats)
    if right_stats_available is None:
        right_stats_available = bool(right_stats)
    left_points = calculate_fantasy_points(left_stats, scoring_settings)
    right_points = calculate_fantasy_points(right_stats, scoring_settings)
    rows: list[str] = []

    for label, stat_name in stat_fields:
        left_value = (
            left_points if stat_name is None else left_stats.get(stat_name, 0) or 0
        )
        right_value = (
            right_points if stat_name is None else right_stats.get(stat_name, 0) or 0
        )
        numeric_left = float(left_value) if isinstance(left_value, Real) else 0.0
        numeric_right = float(right_value) if isinstance(right_value, Real) else 0.0
        displayed_left = truncate_decimal(numeric_left)
        displayed_right = truncate_decimal(numeric_right)
        left_wins = left_stats_available and right_stats_available and (
            numeric_left < numeric_right
            if label in LOWER_IS_BETTER
            else numeric_left > numeric_right
        )
        right_wins = left_stats_available and right_stats_available and (
            numeric_right < numeric_left
            if label in LOWER_IS_BETTER
            else numeric_right > numeric_left
        )
        left_class = " comparison-stat-winner" if left_wins else ""
        right_class = " comparison-stat-winner" if right_wins else ""
        rows.append(
            "<tr>"
            f'<td class="comparison-stat-value comparison-stat-left{left_class}">'
            f"{'—' if not left_stats_available else f'{displayed_left:.2f}'}</td>"
            f'<td class="comparison-stat-label">{escape(label)}</td>'
            f'<td class="comparison-stat-value comparison-stat-right{right_class}">'
            f"{'—' if not right_stats_available else f'{displayed_right:.2f}'}</td>"
            "</tr>"
        )

    left_name = _get_player_name(left_player_id, left_player)
    right_name = _get_player_name(right_player_id, right_player)
    left_meta = (
        f"{left_player.get('team') or 'FA'} · "
        f"{_get_player_position(left_player) or '—'}"
    )
    right_meta = (
        f"{right_player.get('team') or 'FA'} · "
        f"{_get_player_position(right_player) or '—'}"
    )
    return (
        '<section class="comparison-wrapper">'
        '<div class="comparison-player-header">'
        '<div class="comparison-player comparison-player-left">'
        f"<h3>{escape(left_name)}</h3>"
        f'<div class="comparison-player-meta">{escape(left_meta)}</div></div>'
        "<div></div>"
        '<div class="comparison-player comparison-player-right">'
        f"<h3>{escape(right_name)}</h3>"
        f'<div class="comparison-player-meta">{escape(right_meta)}</div></div>'
        "</div>"
        '<table class="comparison-table"><tbody>'
        + "".join(rows)
        + "</tbody></table></section>"
    )


# Compare the two players occupying one matchup position for the selected week.
@st.dialog("Position Comparison", width="large")
def show_player_comparison(
    left_player_id: str | None,
    right_player_id: str | None,
    players: dict[str, dict[str, Any]],
    stats_by_player_id: dict[str, dict[str, Any]],
    scoring_settings: dict[str, Any],
    *,
    stats_source: str | None = None,
    selected_week: int | None = None,
) -> None:
    left_player = players.get(str(left_player_id), {}) if left_player_id else {}
    right_player = players.get(str(right_player_id), {}) if right_player_id else {}
    left_stats = (
        stats_by_player_id.get(str(left_player_id), {}) if left_player_id else {}
    )
    right_stats = (
        stats_by_player_id.get(str(right_player_id), {}) if right_player_id else {}
    )
    stat_fields = get_relevant_stat_fields(
        _get_player_position(left_player),
        _get_player_position(right_player),
    )

    if stats_source is not None and selected_week is not None:
        st.caption(f"{stats_source} · Week {selected_week}")

    st.markdown(
        """
        <style>
            .comparison-player-header {
                align-items: end;
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(8rem, 0.7fr) minmax(0, 1fr);
            }
            .comparison-player h3 { margin-bottom: 0; }
            .comparison-player-right { text-align: right; }
            .comparison-player-meta {
                color: #808495;
                font-size: 0.75rem;
                margin-bottom: 0.75rem;
            }
            .comparison-table {
                border: 0;
                border-collapse: separate;
                border-spacing: 0;
                width: 100%;
            }
            .comparison-table tr:nth-child(odd) {
                background: rgba(128, 128, 128, 0.08);
            }
            .comparison-table tr:nth-child(even) {
                background: rgba(128, 128, 128, 0.025);
            }
            .comparison-table td {
                border: 0;
                padding: 0.55rem 0.7rem;
            }
            .comparison-stat-value {
                font-variant-numeric: tabular-nums;
                font-weight: 650;
                width: 35%;
            }
            .comparison-stat-left { text-align: left; }
            .comparison-stat-right { text-align: right; }
            .comparison-stat-label {
                color: #808495;
                font-size: 0.78rem;
                font-weight: 650;
                text-align: center;
                width: 30%;
            }
            .comparison-stat-winner {
                background: rgba(34, 197, 94, 0.10);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        _render_comparison_table(
            left_player_id,
            left_player,
            left_stats,
            right_player_id,
            right_player,
            right_stats,
            scoring_settings,
            stat_fields,
            left_stats_available=(
                left_player_id is not None
                and str(left_player_id) in stats_by_player_id
            ),
            right_stats_available=(
                right_player_id is not None
                and str(right_player_id) in stats_by_player_id
            ),
        ),
        unsafe_allow_html=True,
    )
