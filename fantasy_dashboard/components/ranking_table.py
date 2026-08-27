from html import escape
from textwrap import dedent
from urllib.parse import quote

import streamlit as st

from fantasy_dashboard.clients.sleeper import SleeperClient
from fantasy_dashboard.standings import StandingRow


# Render the team identity with a compact avatar and muted owner name.
def _render_team_cell(standing: StandingRow) -> str:
    avatar_id = standing.avatar_id
    if avatar_id and avatar_id != "None":
        avatar_url = f"{SleeperClient.AVATAR_URL}/{quote(avatar_id, safe='')}"
        avatar = (
            f'<img class="ranking-avatar" src="{escape(avatar_url)}" '
            f'alt="{escape(standing.team_name)} avatar">'
        )
    else:
        avatar = '<span class="ranking-avatar-fallback">🏈</span>'

    return (
        '<td class="ranking-team">'
        '<div class="ranking-team-identity">'
        f"{avatar}"
        '<div class="ranking-team-text">'
        f'<span class="ranking-team-name">{escape(standing.team_name)}</span>'
        f'<span class="ranking-owner">{escape(standing.display_name)}</span>'
        "</div></div></td>"
    )


# Render league standings as a borderless, zebra-striped table.
def render_ranking_table(standings: list[StandingRow]) -> None:
    table_rows = "".join(
        "<tr>"
        f'<td class="ranking-placement">{standing.placement}</td>'
        f"{_render_team_cell(standing)}"
        f'<td class="ranking-record">{standing.wins}-{standing.losses}-{standing.ties}</td>'
        f'<td class="ranking-points">{standing.points_for:,.2f}</td>'
        f'<td class="ranking-points">{standing.points_against:,.2f}</td>'
        "</tr>"
        for standing in standings
    )

    st.markdown(
        dedent(f"""
        <style>
            .ranking-table {{
                border-collapse: collapse;
                color: inherit;
                width: 100%;
            }}
            .ranking-table th,
            .ranking-table td {{
                border: none;
                padding: 0.65rem 0.85rem;
                text-align: left;
                vertical-align: middle;
            }}
            .ranking-table th {{
                color: #808495;
                font-size: 0.8rem;
                text-transform: uppercase;
            }}
            .ranking-table tbody tr:nth-child(odd) {{
                background-color: rgba(128, 128, 128, 0.10);
            }}
            .ranking-table tbody tr:nth-child(even) {{
                background-color: rgba(128, 128, 128, 0.03);
            }}
            .ranking-table .ranking-placement {{
                color: #808495;
                font-size: 1rem;
                font-weight: 700;
                text-align: center;
                width: 10%;
            }}
            .ranking-table .ranking-team {{
                width: 42%;
            }}
            .ranking-table .ranking-team-identity {{
                align-items: center;
                display: flex;
                gap: 0.6rem;
                min-width: 0;
            }}
            .ranking-table .ranking-avatar,
            .ranking-table .ranking-avatar-fallback {{
                align-items: center;
                border-radius: 50%;
                display: flex;
                flex: 0 0 32px;
                height: 32px;
                justify-content: center;
                object-fit: cover;
                width: 32px;
            }}
            .ranking-table .ranking-avatar-fallback {{
                background: rgba(128, 128, 128, 0.12);
                font-size: 0.9rem;
            }}
            .ranking-table .ranking-team-text {{
                align-items: baseline;
                display: flex;
                gap: 0.45rem;
                min-width: 0;
            }}
            .ranking-table .ranking-team-name {{
                font-weight: 600;
            }}
            .ranking-table .ranking-owner {{
                color: #808495;
                font-size: 0.72rem;
            }}
            .ranking-table .ranking-record {{
                text-align: center;
                white-space: nowrap;
                width: 14%;
            }}
            .ranking-table .ranking-points,
            .ranking-table th.ranking-points {{
                font-variant-numeric: tabular-nums;
                text-align: right;
                white-space: nowrap;
                width: 17%;
            }}
        </style>
        <table class="ranking-table">
            <thead>
                <tr>
                    <th>Placement</th>
                    <th>Team Name</th>
                    <th class="ranking-record">W-L-D</th>
                    <th class="ranking-points">Points For</th>
                    <th class="ranking-points">Points Against</th>
                </tr>
            </thead>
            <tbody>{table_rows}</tbody>
        </table>
        """),
        unsafe_allow_html=True,
    )
