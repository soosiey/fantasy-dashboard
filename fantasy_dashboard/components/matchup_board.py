from dataclasses import dataclass
from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.components.roster_table import render_injury_badge
from fantasy_dashboard.matchups import (
    HeadToHeadMatchup,
    MatchupPlayer,
    MatchupTeam,
)

MATCHUP_COLUMN_WIDTHS = [1, 0.12, 1]


# Identify the two players selected through a matchup position badge.
@dataclass(frozen=True, slots=True)
class PlayerComparisonSelection:
    left_player_id: str | None
    right_player_id: str | None


# Render one team placard with its weekly score on the outside edge.
def _render_team_placard(team: MatchupTeam, side: str) -> str:
    to_play = f'<span class="matchup-to-play">({team.to_play_count})</span>'
    owner_content = (
        f"{to_play}<span>{escape(team.display_name)}</span>"
        if side == "left"
        else f"<span>{escape(team.display_name)}</span>{to_play}"
    )
    owner = (
        f'<div class="matchup-owner matchup-owner-{side}">{owner_content}</div>'
        if team.display_name
        else ""
    )
    identity = (
        '<div class="matchup-team-identity">'
        f'<div class="matchup-team-name">{escape(team.team_name)}</div>{owner}'
        "</div>"
    )
    displayed_score = "—" if team.points is None else f"{team.points:,.2f}"
    score = f'<div class="matchup-score">{displayed_score}</div>'
    content = score + identity if side == "left" else identity + score
    return f'<div class="matchup-placard matchup-placard-{side}">{content}</div>'


# Render one player with muted NFL-team and weekly-opponent metadata.
def _render_player(
    player: MatchupPlayer,
    side: str,
    is_starter: bool = True,
) -> str:
    metadata_parts = [escape(player.nfl_team)] if player.nfl_team else []
    if player.opponent:
        metadata_parts.append(escape(player.opponent))
    metadata = (
        f'<div class="matchup-player-team">{" ".join(metadata_parts)}</div>'
        if metadata_parts
        else ""
    )
    identity = (
        '<div class="matchup-player-identity">'
        '<div class="matchup-player-name">'
        f"{render_injury_badge(player.injury_status)}"
        f"<span>{escape(player.name)}</span></div>{metadata}</div>"
    )
    displayed_score = "—" if player.points is None else f"{player.points:g}"
    score = f'<div class="matchup-player-score">{displayed_score}</div>'
    content = score + identity if side == "left" else identity + score
    status_class = (
        f" matchup-player-status-{player.game_status}"
        if player.game_status in {"to-play", "playing", "finished"}
        else ""
    )
    attention_class = (
        " matchup-player-attention"
        if is_starter
        and (
            player.player_id is None or player.is_inactive or bool(player.injury_status)
        )
        else ""
    )
    return (
        f'<div class="matchup-player matchup-player-{side}'
        f'{status_class}{attention_class}">'
        f"{content}</div>"
    )


# Render all weekly pairings with mirrored lineups around position bubbles.
def render_matchup_board(
    matchups: list[HeadToHeadMatchup], context_key: str = "board"
) -> str | PlayerComparisonSelection | None:
    if not matchups:
        st.info("No matchups are available for this week.")
        return None

    st.markdown(
        dedent("""
        <style>
            [class*="st-key-matchup-header-"] {
                margin-bottom: 0.65rem;
            }
            .matchup-placard {
                align-items: center;
                background: rgba(128, 128, 128, 0.09);
                border-radius: 0.65rem;
                display: flex;
                justify-content: space-between;
                min-height: 4.5rem;
                padding: 0.75rem 1rem;
            }
            .matchup-team-identity {
                min-width: 0;
            }
            .matchup-placard-left .matchup-team-identity {
                text-align: right;
            }
            .matchup-team-name {
                font-size: 1rem;
                font-weight: 700;
            }
            .matchup-owner {
                align-items: center;
                color: #808495;
                display: flex;
                font-size: 0.72rem;
                gap: 0.3rem;
                margin-top: 0.1rem;
            }
            .matchup-owner-left { justify-content: flex-end; }
            .matchup-owner-right { justify-content: flex-start; }
            .matchup-score {
                font-size: 1.15rem;
                font-variant-numeric: tabular-nums;
                font-weight: 800;
            }
            .matchup-placard-left .matchup-score {
                margin-right: 0.75rem;
            }
            .matchup-placard-right .matchup-score {
                margin-left: 0.75rem;
            }
            .matchup-versus {
                color: #808495;
                font-size: 0.72rem;
                font-weight: 800;
                text-align: center;
            }
            .matchup-lineup {
                margin-top: 0.65rem;
            }
            [class*="st-key-matchup-lineup-row-"] {
                border-radius: 0.2rem;
                min-height: 3.25rem;
                padding: 0.35rem 1rem;
            }
            [class*="st-key-matchup-lineup-row-odd-"] {
                background: rgba(128, 128, 128, 0.08);
            }
            [class*="st-key-matchup-lineup-row-even-"] {
                background: rgba(128, 128, 128, 0.025);
            }
            [class*="st-key-matchup-lineup-row-bench-"] {
                border-top: 1px solid rgba(128, 128, 128, 0.35);
                margin-top: 0.4rem;
                padding-top: 0.75rem;
            }
            .matchup-player {
                align-items: center;
                border: 1px solid transparent;
                border-radius: 0.4rem;
                box-sizing: border-box;
                display: flex;
                font-size: 0.88rem;
                font-weight: 600;
                justify-content: space-between;
                min-width: 0;
                padding: 0.3rem 0.45rem;
                position: relative;
                transform: translateY(-0.4rem);
            }
            .matchup-player-status-to-play {
                background: rgba(239, 68, 68, 0.16);
            }
            .matchup-player-status-playing {
                background: rgba(249, 115, 22, 0.18);
            }
            .matchup-player-status-finished {
                background: rgba(34, 197, 94, 0.16);
            }
            .matchup-player-attention {
                border-color: rgba(249, 115, 22, 0.42);
            }
            [class*="st-key-matchup-player-click-"] {
                border-radius: 0.35rem;
                cursor: pointer;
                min-height: 2.7rem;
                padding: 0.35rem 0.45rem;
                position: relative;
                transition: background-color 120ms ease;
            }
            [class*="st-key-matchup-player-click-"]:hover {
                background: rgba(99, 102, 241, 0.13);
            }
            [class*="st-key-matchup-player-click-"]
                [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
                inset: 0;
                position: absolute !important;
                z-index: 2;
            }
            [class*="st-key-matchup-player-click-"] [data-testid="stButton"] {
                height: 100%;
                width: 100%;
            }
            [class*="st-key-matchup-player-click-"] [data-testid="stButton"] button {
                height: 100%;
                opacity: 0;
                width: 100%;
            }
            [class*="st-key-matchup-position-click-"] {
                align-items: center;
                display: flex;
                justify-content: center;
                min-height: 2.7rem;
            }
            [class*="st-key-matchup-position-click-"] [data-testid="stButton"] {
                display: flex;
                justify-content: center;
                width: 100%;
            }
            [class*="st-key-matchup-position-click-"] [data-testid="stButton"] button {
                aspect-ratio: 1;
                background: rgba(37, 99, 235, 0.14);
                border: 0;
                border-radius: 50%;
                color: #3b82f6;
                font-size: 0.58rem;
                font-weight: 800;
                height: 2.35rem;
                min-height: 2.35rem;
                padding: 0;
                width: 2.35rem;
            }
            [class*="st-key-matchup-position-click-"]
                [data-testid="stButton"] button:hover {
                background: rgba(37, 99, 235, 0.24);
                color: #3b82f6;
            }
            .matchup-player-left {
                text-align: right;
            }
            .matchup-player-right {
                text-align: left;
            }
            .matchup-player-identity {
                min-width: 0;
            }
            .matchup-player-name {
                display: inline-block;
                position: relative;
            }
            .matchup-player-name .injury-status {
                border-radius: 0.25rem;
                color: white;
                display: inline-block;
                font-size: 0.58rem;
                font-weight: 700;
                line-height: 1;
                padding: 0.08rem 0.25rem;
                position: absolute;
                right: calc(100% + 0.35rem);
                top: 50%;
                transform: translateY(-50%);
            }
            .matchup-player-right .matchup-player-name .injury-status {
                left: calc(100% + 0.35rem);
                right: auto;
            }
            .matchup-player-name .injury-questionable { background: #f59e0b; }
            .matchup-player-name .injury-doubtful { background: #ca8a04; }
            .matchup-player-name .injury-out,
            .matchup-player-name .injury-ir { background: #dc2626; }
            .matchup-player-name .injury-pup,
            .matchup-player-name .injury-suspended { background: #7c3aed; }
            .matchup-player-name .injury-inactive,
            .matchup-player-name .injury-unknown { background: #6b7280; }
            .matchup-player-name .injury-dnr { background: #2563eb; }
            .matchup-player-name .injury-covid { background: #0f766e; }
            .matchup-player-score {
                font-variant-numeric: tabular-nums;
                font-weight: 700;
            }
            .matchup-player-left .matchup-player-score {
                margin-right: 0.75rem;
            }
            .matchup-player-right .matchup-player-score {
                margin-left: 0.75rem;
            }
            .matchup-player-team {
                color: #808495;
                font-size: 0.68rem;
                font-weight: 400;
                margin-top: 0.05rem;
            }
            .matchup-position {
                align-items: center;
                aspect-ratio: 1;
                background: rgba(37, 99, 235, 0.14);
                border-radius: 50%;
                color: #3b82f6;
                display: flex;
                font-size: 0.58rem;
                font-weight: 800;
                justify-content: center;
                left: 50%;
                position: relative;
                text-align: center;
                transform: translateX(-50%);
                width: 2.35rem;
            }
        </style>
        """),
        unsafe_allow_html=True,
    )

    selected_player_id = None
    for matchup_index, matchup in enumerate(matchups):
        with st.container(key=f"matchup-header-{context_key}-{matchup_index}"):
            left_header, versus_header, right_header = st.columns(
                MATCHUP_COLUMN_WIDTHS,
                vertical_alignment="center",
                gap="medium",
            )
            left_header.markdown(
                _render_team_placard(matchup.left_team, "left"),
                unsafe_allow_html=True,
            )
            versus_header.markdown(
                '<div class="matchup-versus">VS</div>',
                unsafe_allow_html=True,
            )
            right_header.markdown(
                _render_team_placard(matchup.right_team, "right"),
                unsafe_allow_html=True,
            )

        for row_index, row in enumerate(matchup.lineup):
            shade = "odd" if row_index % 2 == 0 else "even"
            bench = "bench-" if row.position == "BN" else ""
            row_key = (
                f"matchup-lineup-row-{bench}{shade}-{context_key}-"
                f"{matchup_index}-{row_index}"
            )
            with st.container(key=row_key):
                left_column, position_column, right_column = st.columns(
                    MATCHUP_COLUMN_WIDTHS,
                    vertical_alignment="center",
                    gap="medium",
                )
                for side, column, player in (
                    ("left", left_column, row.left_player),
                    ("right", right_column, row.right_player),
                ):
                    with (
                        column,
                        st.container(
                            key=(
                                f"matchup-player-click-{context_key}-{matchup_index}-"
                                f"{row_index}-{side}"
                            )
                        ),
                    ):
                        st.markdown(
                            _render_player(
                                player,
                                side,
                                is_starter=row.position != "BN",
                            ),
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

                with (
                    position_column,
                    st.container(
                        key=(
                            f"matchup-position-click-{context_key}-{matchup_index}-"
                            f"{row_index}"
                        )
                    ),
                ):
                    has_player = (
                        row.left_player.player_id is not None
                        or row.right_player.player_id is not None
                    )
                    if has_player:
                        if st.button(
                            row.position,
                            key=(
                                f"matchup-position-button-{context_key}-"
                                f"{matchup_index}-{row_index}"
                            ),
                            width="content",
                        ):
                            selected_player_id = PlayerComparisonSelection(
                                left_player_id=row.left_player.player_id,
                                right_player_id=row.right_player.player_id,
                            )
                    else:
                        st.markdown(
                            f'<div class="matchup-position">{escape(row.position)}</div>',
                            unsafe_allow_html=True,
                        )

    return selected_player_id


# Select one matchup with dots and arrows, defaulting to the signed-in user's game.
def render_matchup_carousel(
    matchups: list[HeadToHeadMatchup],
    current_user_id: str | None,
    context_key: str,
) -> str | PlayerComparisonSelection | None:
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
    ordered_matchups = matchups[user_matchup_index:] + matchups[:user_matchup_index]

    state_key = f"selected-matchup-v2-{context_key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    selected_index = min(int(st.session_state[state_key]), len(ordered_matchups) - 1)
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
    return render_matchup_board([ordered_matchups[selected_index]], context_key)
