from html import escape
from textwrap import dedent

import streamlit as st

INJURY_STATUS_DISPLAY = {
    "Questionable": ("Q", "questionable"),
    "Doubtful": ("D", "doubtful"),
    "Out": ("O", "out"),
    "IR": ("IR", "ir"),
    "PUP": ("PUP", "pup"),
    "Sus": ("SUS", "suspended"),
    "NA": ("NA", "inactive"),
    "DNR": ("DNR", "dnr"),
    "COV": ("COV", "covid"),
}

RosterRow = tuple[str, str, str | None, str | None, str | None, str | None]


# Render a compact injury marker before the player's name.
def render_injury_badge(injury_status: str | None) -> str:
    if not injury_status:
        return ""

    label, css_class = INJURY_STATUS_DISPLAY.get(
        injury_status, (injury_status.upper(), "unknown")
    )
    return (
        f'<span class="injury-status injury-{css_class}" '
        f'title="{escape(injury_status)}">{escape(label)}</span>'
    )


# Combine the player's primary name line and muted team metadata.
def _render_player_cell(
    player_name: str,
    player_position: str | None,
    injury_status: str | None,
    player_team: str | None,
) -> str:
    position = (
        f'<span class="player-position">{escape(player_position)}</span>'
        if player_position
        else ""
    )
    team = (
        f'<div class="player-team">{escape(player_team)}</div>' if player_team else ""
    )
    return (
        '<div class="roster-player">'
        '<div class="player-primary">'
        f"{render_injury_badge(injury_status)}{escape(player_name)}{position}"
        "</div>"
        f"{team}</div>"
    )


# Apply the table-like styling shared by native Streamlit roster rows.
def _render_roster_styles() -> None:
    st.markdown(
        dedent("""
        <style>
            .roster-header {
                color: #808495;
                font-size: 0.8rem;
                font-weight: 600;
                padding: 0 0.85rem 0.2rem;
                text-transform: uppercase;
            }
            .roster-header-news {
                text-align: right;
            }
            [class*="st-key-roster-row-"] {
                border-radius: 0.2rem;
                padding: 0.5rem 0.85rem;
            }
            [class*="st-key-roster-row-odd-"] {
                background-color: rgba(128, 128, 128, 0.10);
            }
            [class*="st-key-roster-row-even-"] {
                background-color: rgba(128, 128, 128, 0.03);
            }
            [class*="st-key-roster-row-"] [data-testid="stButton"] {
                display: flex;
                justify-content: flex-end;
            }
            [class*="st-key-roster-row-"] [data-testid="stButton"] button {
                font-size: 0.75rem;
                white-space: nowrap;
            }
            .roster-position {
                color: #808495;
                font-weight: 600;
            }
            .roster-player .player-position {
                color: #808495;
                font-size: 0.78rem;
                margin-left: 0.5rem;
            }
            .roster-player .player-primary {
                position: relative;
            }
            .roster-player .player-team {
                color: #808495;
                font-size: 0.72rem;
                margin-top: 0.08rem;
            }
            .roster-player .injury-status {
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
            .roster-player .injury-questionable { background: #f59e0b; }
            .roster-player .injury-doubtful { background: #ca8a04; }
            .roster-player .injury-out,
            .roster-player .injury-ir { background: #dc2626; }
            .roster-player .injury-pup,
            .roster-player .injury-suspended { background: #7c3aed; }
            .roster-player .injury-inactive,
            .roster-player .injury-unknown { background: #6b7280; }
            .roster-player .injury-dnr { background: #2563eb; }
            .roster-player .injury-covid { background: #0f766e; }
        </style>
        """),
        unsafe_allow_html=True,
    )


# Render table-like rows with native buttons and return the selected player ID.
def render_roster_table(rows: list[RosterRow]) -> str | None:
    _render_roster_styles()

    position_header, player_header, news_header = st.columns([2, 5, 2])
    position_header.markdown('<div class="roster-header">Position</div>', True)
    player_header.markdown('<div class="roster-header">Player</div>', True)
    news_header.markdown(
        '<div class="roster-header roster-header-news">News</div>', True
    )

    selected_player_id = None
    for index, row in enumerate(rows):
        (
            position,
            player_name,
            player_position,
            injury_status,
            player_team,
            player_id,
        ) = row
        shade = "odd" if index % 2 == 0 else "even"

        with st.container(key=f"roster-row-{shade}-{index}"):
            position_column, player_column, news_column = st.columns(
                [2, 5, 2], vertical_alignment="center"
            )
            position_column.markdown(
                f'<div class="roster-position">{escape(position)}</div>',
                unsafe_allow_html=True,
            )
            player_column.markdown(
                _render_player_cell(
                    player_name,
                    player_position,
                    injury_status,
                    player_team,
                ),
                unsafe_allow_html=True,
            )

            has_player = player_id is not None
            if news_column.button(
                "View Recent News" if has_player else "News unavailable",
                key=f"player-news-{index}-{player_id}",
                disabled=not has_player,
                width="stretch",
            ):
                selected_player_id = player_id

    return selected_player_id
