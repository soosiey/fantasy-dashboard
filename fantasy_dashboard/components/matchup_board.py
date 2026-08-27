from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.matchups import (
    HeadToHeadMatchup,
    MatchupPlayer,
    MatchupTeam,
)


# Render one team placard with its owner and weekly score.
def _render_team_placard(team: MatchupTeam) -> str:
    owner = (
        f'<div class="matchup-owner">{escape(team.display_name)}</div>'
        if team.display_name
        else ""
    )
    return (
        '<div class="matchup-placard">'
        '<div class="matchup-team-identity">'
        f'<div class="matchup-team-name">{escape(team.team_name)}</div>{owner}'
        "</div>"
        f'<div class="matchup-score">{team.points:,.2f}</div>'
        "</div>"
    )


# Render one player with muted NFL-team metadata.
def _render_player(player: MatchupPlayer, side: str) -> str:
    nfl_team = (
        f'<div class="matchup-player-team">{escape(player.nfl_team)}</div>'
        if player.nfl_team
        else ""
    )
    return (
        f'<div class="matchup-player matchup-player-{side}">'
        f'<div>{escape(player.name)}</div>{nfl_team}</div>'
    )


# Render all weekly pairings with mirrored lineups around position bubbles.
def render_matchup_board(matchups: list[HeadToHeadMatchup]) -> None:
    if not matchups:
        st.info("No matchups are available for this week.")
        return

    matchup_sections = "".join(
        '<section class="matchup-card">'
        '<div class="matchup-header">'
        f"{_render_team_placard(matchup.left_team)}"
        '<div class="matchup-versus">VS</div>'
        f"{_render_team_placard(matchup.right_team)}"
        "</div>"
        '<div class="matchup-lineup">'
        + "".join(
            '<div class="matchup-lineup-row">'
            f"{_render_player(row.left_player, 'left')}"
            f'<div class="matchup-position">{escape(row.position)}</div>'
            f"{_render_player(row.right_player, 'right')}"
            "</div>"
            for row in matchup.lineup
        )
        + "</div></section>"
        for matchup in matchups
    )
    st.markdown(
        dedent(f"""
        <style>
            .matchup-card {{
                margin: 0 0 2rem;
            }}
            .matchup-header,
            .matchup-lineup-row {{
                align-items: center;
                display: grid;
                gap: 1rem;
                grid-template-columns: minmax(0, 1fr) 3rem minmax(0, 1fr);
            }}
            .matchup-placard {{
                align-items: center;
                background: rgba(128, 128, 128, 0.09);
                border-radius: 0.65rem;
                display: flex;
                justify-content: space-between;
                min-height: 4.5rem;
                padding: 0.75rem 1rem;
            }}
            .matchup-team-identity {{
                min-width: 0;
            }}
            .matchup-team-name {{
                font-size: 1rem;
                font-weight: 700;
            }}
            .matchup-owner {{
                color: #808495;
                font-size: 0.72rem;
                margin-top: 0.1rem;
            }}
            .matchup-score {{
                font-size: 1.15rem;
                font-variant-numeric: tabular-nums;
                font-weight: 800;
                margin-left: 0.75rem;
            }}
            .matchup-versus {{
                color: #808495;
                font-size: 0.72rem;
                font-weight: 800;
                text-align: center;
            }}
            .matchup-lineup {{
                margin-top: 0.65rem;
            }}
            .matchup-lineup-row {{
                min-height: 3.25rem;
                padding: 0.35rem 1rem;
            }}
            .matchup-lineup-row:nth-child(odd) {{
                background: rgba(128, 128, 128, 0.08);
            }}
            .matchup-lineup-row:nth-child(even) {{
                background: rgba(128, 128, 128, 0.025);
            }}
            .matchup-player {{
                font-size: 0.88rem;
                font-weight: 600;
                min-width: 0;
            }}
            .matchup-player-left {{
                text-align: right;
            }}
            .matchup-player-right {{
                text-align: left;
            }}
            .matchup-player-team {{
                color: #808495;
                font-size: 0.68rem;
                font-weight: 400;
                margin-top: 0.05rem;
            }}
            .matchup-position {{
                align-items: center;
                aspect-ratio: 1;
                background: rgba(37, 99, 235, 0.14);
                border-radius: 50%;
                color: #3b82f6;
                display: flex;
                font-size: 0.58rem;
                font-weight: 800;
                justify-content: center;
                margin: auto;
                text-align: center;
                width: 2.35rem;
            }}
        </style>
        <div class="matchup-board">{matchup_sections}</div>
        """),
        unsafe_allow_html=True,
    )


# Select one matchup with dots and arrows, defaulting to the signed-in user's game.
def render_matchup_carousel(
    matchups: list[HeadToHeadMatchup],
    current_user_id: str | None,
    context_key: str,
) -> None:
    if not matchups:
        render_matchup_board([])
        return

    # Rotate the signed-in user's matchup to the first carousel position.
    user_matchup_index = next(
        (
            index
            for index, matchup in enumerate(matchups)
            if current_user_id is not None
            and current_user_id
            in {matchup.left_team.user_id, matchup.right_team.user_id}
        ),
        0,
    )
    ordered_matchups = (
        matchups[user_matchup_index:] + matchups[:user_matchup_index]
    )

    state_key = f"selected-matchup-v2-{context_key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    selected_index = min(
        int(st.session_state[state_key]), len(ordered_matchups) - 1
    )
    dots_placeholder = st.empty()
    _, previous_column, next_column, _ = st.columns([5, 1, 1, 5])
    if previous_column.button(
        "‹",
        key=f"previous-{context_key}",
        help="Previous matchup",
        disabled=len(ordered_matchups) == 1,
        width="stretch",
    ):
        selected_index = (selected_index - 1) % len(ordered_matchups)
    if next_column.button(
        "›",
        key=f"next-{context_key}",
        help="Next matchup",
        disabled=len(ordered_matchups) == 1,
        width="stretch",
    ):
        selected_index = (selected_index + 1) % len(ordered_matchups)

    st.session_state[state_key] = selected_index
    dots = "".join(
        "●" if index == selected_index else "○"
        for index in range(len(ordered_matchups))
    )
    dots_placeholder.markdown(
        f'<div class="matchup-dots" title="Matchup {selected_index + 1} of '
        f'{len(ordered_matchups)}">{dots}</div>'
        "<style>.matchup-dots { color: #808495; font-size: 0.7rem; "
        "letter-spacing: 0.25rem; text-align: center; }</style>",
        unsafe_allow_html=True,
    )
    render_matchup_board([ordered_matchups[selected_index]])
