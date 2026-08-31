from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.draft import DraftResultRow


# Format auction prices without implying a cost for snake-draft selections.
def _format_amount(amount: float | None) -> str:
    if amount is None:
        return ""
    if amount.is_integer():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


# Render draft results as a compact, borderless, zebra-striped table.
def render_draft_table(
    rows: list[DraftResultRow], *, show_round: bool | None = None
) -> None:
    if show_round is None:
        show_round = not any(row.amount is not None for row in rows)
    round_cells = (
        [f'<td class="draft-round">{row.round_number}</td>' for row in rows]
        if show_round
        else [""] * len(rows)
    )
    table_rows = "".join(
        "<tr>"
        f'<td class="draft-pick">{row.pick_number}</td>'
        f"{round_cell}"
        f'<td class="draft-player">{escape(row.player_name)}</td>'
        f'<td class="draft-user">{escape(row.drafted_by)}</td>'
        f'<td class="draft-amount">{_format_amount(row.amount)}</td>'
        "</tr>"
        for row, round_cell in zip(rows, round_cells, strict=True)
    )
    round_header = "<th>Round</th>" if show_round else ""
    player_width = "36%" if show_round else "46%"

    st.markdown(
        dedent(f"""
        <style>
            .draft-table {{
                border-collapse: collapse;
                color: inherit;
                width: 100%;
            }}
            .draft-table th,
            .draft-table td {{
                border: none;
                padding: 0.7rem 0.9rem;
                vertical-align: middle;
            }}
            .draft-table th {{
                color: #808495;
                font-size: 0.8rem;
                text-transform: uppercase;
            }}
            .draft-table tbody tr:nth-child(odd) {{
                background-color: rgba(128, 128, 128, 0.10);
            }}
            .draft-table tbody tr:nth-child(even) {{
                background-color: rgba(128, 128, 128, 0.03);
            }}
            .draft-table .draft-pick,
            .draft-table .draft-round {{
                color: #808495;
                font-variant-numeric: tabular-nums;
                text-align: center;
                width: 10%;
            }}
            .draft-table .draft-player {{
                font-weight: 600;
                width: {player_width};
            }}
            .draft-table .draft-user {{
                color: #a0a4b2;
                width: 25%;
            }}
            .draft-table .draft-amount,
            .draft-table th:last-child {{
                font-variant-numeric: tabular-nums;
                text-align: right;
                width: 19%;
            }}
        </style>
        <table class="draft-table">
            <thead>
                <tr>
                    <th>Pick Number</th>
                    {round_header}
                    <th>Player</th>
                    <th>Drafted By</th>
                    <th>Money Spent</th>
                </tr>
            </thead>
            <tbody>{table_rows}</tbody>
        </table>
        """),
        unsafe_allow_html=True,
    )
