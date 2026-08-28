from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.matchups import (
    HeadToHeadMatchup,
    MatchupPlayer,
    MatchupTeam,
)


# Render one team placard with its weekly score on the outside edge.
def _render_team_placard(team: MatchupTeam, side: str) -> str:
    owner = (
        f'<div class="matchup-owner">{escape(team.display_name)}</div>'
        if team.display_name
        else ""
    )
    identity = (
        '<div class="matchup-team-identity">'
        f'<div class="matchup-team-name">{escape(team.team_name)}</div>{owner}'
        "</div>"
    )
    score = f'<div class="matchup-score">{team.points:,.2f}</div>'
    content = score + identity if side == "left" else identity + score
    return f'<div class="matchup-placard matchup-placard-{side}">{content}</div>'


# Render one player with muted NFL-team metadata.
def _render_player(player: MatchupPlayer, side: str) -> str:
    nfl_team = (
        f'<div class="matchup-player-team">{escape(player.nfl_team)}</div>'
        if player.nfl_team
        else ""
    )
    identity = (
        '<div class="matchup-player-identity">'
        f'<div>{escape(player.name)}</div>{nfl_team}</div>'
    )
    score = f'<div class="matchup-player-score">{player.points:g}</div>'
    content = score + identity if side == "left" else identity + score
    return f'<div class="matchup-player matchup-player-{side}">{content}</div>'


# Render all weekly pairings with mirrored lineups around position bubbles.
def render_matchup_board(
    matchups: list[HeadToHeadMatchup], context_key: str = "board"
) -> str | None:
    if not matchups:
        st.info("No matchups are available for this week.")
        return None

    st.markdown(
        dedent(f"""
        <style>
            .matchup-card {{
                margin: 0 0 0.65rem;
            }}
            .matchup-header {{
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
            .matchup-placard-left .matchup-team-identity {{
                text-align: right;
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
            }}
            .matchup-placard-left .matchup-score {{
                margin-right: 0.75rem;
            }}
            .matchup-placard-right .matchup-score {{
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
            [class*="st-key-matchup-lineup-row-"] {{
                border-radius: 0.2rem;
                min-height: 3.25rem;
                padding: 0.35rem 1rem;
            }}
            [class*="st-key-matchup-lineup-row-odd-"] {{
                background: rgba(128, 128, 128, 0.08);
            }}
            [class*="st-key-matchup-lineup-row-even-"] {{
                background: rgba(128, 128, 128, 0.025);
            }}
            [class*="st-key-matchup-lineup-row-bench-"] {{
                border-top: 1px solid rgba(128, 128, 128, 0.35);
                margin-top: 0.4rem;
                padding-top: 0.75rem;
            }}
            .matchup-player {{
                align-items: center;
                display: flex;
                font-size: 0.88rem;
                font-weight: 600;
                justify-content: space-between;
                min-width: 0;
            }}
            [class*="st-key-matchup-player-click-"] {{
                border-radius: 0.35rem;
                cursor: pointer;
                padding: 0.35rem 0.45rem;
                position: relative;
                transition: background-color 120ms ease;
            }}
            [class*="st-key-matchup-player-click-"]:hover {{
                background: rgba(99, 102, 241, 0.13);
            }}
            [class*="st-key-matchup-player-click-"] [data-testid="stButton"] {{
                inset: 0;
                position: absolute;
                z-index: 2;
            }}
            [class*="st-key-matchup-player-click-"] [data-testid="stButton"] button {{
                height: 100%;
                opacity: 0;
                width: 100%;
            }}
            .matchup-player-left {{
                text-align: right;
            }}
            .matchup-player-right {{
                text-align: left;
            }}
            .matchup-player-identity {{
                min-width: 0;
            }}
            .matchup-player-score {{
                font-variant-numeric: tabular-nums;
                font-weight: 700;
            }}
            .matchup-player-left .matchup-player-score {{
                margin-right: 0.75rem;
            }}
            .matchup-player-right .matchup-player-score {{
                margin-left: 0.75rem;
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
        """),
        unsafe_allow_html=True,
    )

    selected_player_id = None
    for matchup_index, matchup in enumerate(matchups):
        header = (
            '<section class="matchup-card"><div class="matchup-header">'
            f"{_render_team_placard(matchup.left_team, 'left')}"
            '<div class="matchup-versus">VS</div>'
            f"{_render_team_placard(matchup.right_team, 'right')}"
            "</div></section>"
        )
        st.markdown(header, unsafe_allow_html=True)

        for row_index, row in enumerate(matchup.lineup):
            shade = "odd" if row_index % 2 == 0 else "even"
            bench = "bench-" if row.position == "BN" else ""
            row_key = (
                f"matchup-lineup-row-{bench}{shade}-{context_key}-"
                f"{matchup_index}-{row_index}"
            )
            with st.container(key=row_key):
                left_column, position_column, right_column = st.columns(
                    [1, 0.12, 1], vertical_alignment="center", gap="medium"
                )
                for side, column, player in (
                    ("left", left_column, row.left_player),
                    ("right", right_column, row.right_player),
                ):
                    with column, st.container(
                        key=(
                            f"matchup-player-click-{context_key}-{matchup_index}-"
                            f"{row_index}-{side}"
                        )
                    ):
                        st.markdown(
                            _render_player(player, side),
                            unsafe_allow_html=True,
                        )
                        if player.player_id is not None and st.button(
                            f"View {player.name} details",
                            key=(
                                f"matchup-player-button-{context_key}-"
                                f"{matchup_index}-{row_index}-{side}"
                            ),
                            width="stretch",
                        ):
                            selected_player_id = player.player_id

                position_column.markdown(
                    f'<div class="matchup-position">{escape(row.position)}</div>',
                    unsafe_allow_html=True,
                )

    return selected_player_id


# Select one matchup with dots and arrows, defaulting to the signed-in user's game.
def render_matchup_carousel(
    matchups: list[HeadToHeadMatchup],
    current_user_id: str | None,
    context_key: str,
) -> str | None:
    if not matchups:
        return render_matchup_board([], context_key)

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
    return render_matchup_board(
        [ordered_matchups[selected_index]], context_key
    )
