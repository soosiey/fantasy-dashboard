from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.playoffs import PlayoffMatchup, PlayoffSlot


# Render a team or unresolved source inside one matchup card.
def _render_slot(slot: PlayoffSlot) -> str:
    css_class = " bracket-slot-winner" if slot.is_winner else ""
    winner_icon = '<span class="bracket-winner-icon">✓</span>' if slot.is_winner else ""
    seed = (
        f'<span class="bracket-seed">{slot.seed}</span>'
        if slot.seed is not None
        else ""
    )
    return (
        f'<div class="bracket-slot{css_class}">'
        '<span class="bracket-team-label">'
        f"<span>{escape(slot.label)}</span>{seed}</span>{winner_icon}</div>"
    )


# Render one playoff matchup with its two participants.
def _render_matchup(matchup: PlayoffMatchup) -> str:
    return (
        '<div class="bracket-matchup">'
        '<div class="bracket-matchup-title">'
        f"{escape(matchup.title)}</div>"
        f"{_render_slot(matchup.team_1)}"
        f"{_render_slot(matchup.team_2)}"
        "</div>"
    )


# Render playoff rounds as horizontally scrolling tournament columns.
def render_playoff_bracket(rounds: dict[int, list[PlayoffMatchup]]) -> None:
    if not rounds:
        st.info("The playoff bracket is not available yet.")
        return

    round_columns = "".join(
        '<section class="bracket-round">'
        f'<h3 class="bracket-round-title">Round {round_number}</h3>'
        '<div class="bracket-round-matchups">'
        f"{''.join(_render_matchup(matchup) for matchup in matchups)}"
        "</div></section>"
        for round_number, matchups in sorted(rounds.items())
    )
    st.markdown(
        dedent(f"""
        <style>
            .playoff-bracket-scroll {{
                overflow-x: auto;
                padding: 0.5rem 0 1rem;
                width: 100%;
            }}
            .playoff-bracket {{
                align-items: stretch;
                display: flex;
                gap: 3rem;
                min-height: 34rem;
                min-width: max-content;
            }}
            .bracket-round {{
                display: flex;
                flex-direction: column;
                min-width: 15rem;
                width: 15rem;
            }}
            .bracket-round-title {{
                color: #808495;
                font-size: 0.8rem;
                margin: 0 0 0.75rem;
                text-align: center;
                text-transform: uppercase;
            }}
            .bracket-round-matchups {{
                display: flex;
                flex: 1;
                flex-direction: column;
                gap: 1.25rem;
                justify-content: space-around;
            }}
            .bracket-matchup {{
                background: rgba(128, 128, 128, 0.06);
                border: 1px solid rgba(128, 128, 128, 0.22);
                border-radius: 0.55rem;
                position: relative;
            }}
            .bracket-round:not(:last-child) .bracket-matchup::after {{
                border-top: 1px solid rgba(128, 128, 128, 0.35);
                content: "";
                position: absolute;
                right: -3rem;
                top: 50%;
                width: 3rem;
            }}
            .bracket-matchup-title {{
                color: #808495;
                font-size: 0.68rem;
                font-weight: 700;
                padding: 0.35rem 0.65rem 0.25rem;
                text-transform: uppercase;
            }}
            .bracket-slot {{
                align-items: center;
                border-top: 1px solid rgba(128, 128, 128, 0.16);
                display: flex;
                font-size: 0.84rem;
                justify-content: space-between;
                min-height: 2.25rem;
                padding: 0.45rem 0.65rem;
            }}
            .bracket-slot-winner {{
                background: rgba(34, 197, 94, 0.10);
                font-weight: 700;
            }}
            .bracket-team-label {{
                align-items: baseline;
                display: flex;
                gap: 0.35rem;
                min-width: 0;
            }}
            .bracket-seed {{
                color: #808495;
                font-size: 0.68rem;
                font-weight: 500;
            }}
            .bracket-winner-icon {{
                color: #16a34a;
                font-weight: 800;
                margin-left: 0.5rem;
            }}
        </style>
        <div class="playoff-bracket-scroll">
            <div class="playoff-bracket">{round_columns}</div>
        </div>
        """),
        unsafe_allow_html=True,
    )
