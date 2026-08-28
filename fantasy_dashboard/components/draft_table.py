from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.draft import DraftResultRow


# Format auction prices without implying a cost for snake-draft selections.
def _format_amount(amount: float | None) -> str:
    if amount is None:
        return "&mdash;"
    if amount.is_integer():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


# Render draft results as a compact, borderless, zebra-striped table.
def render_draft_table(rows: list[DraftResultRow]) -> None:
    table_rows = "".join(
        "<tr>"
        f'<td class="draft-pick">{row.pick_number}</td>'
        f'<td class="draft-player">{escape(row.player_name)}</td>'
        f'<td class="draft-user">{escape(row.drafted_by)}</td>'
        f'<td class="draft-amount">{_format_amount(row.amount)}</td>'
        "</tr>"
        for row in rows
    )

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
            .draft-table th:first-child {{
                color: #808495;
                font-variant-numeric: tabular-nums;
                text-align: center;
                width: 14%;
            }}
            .draft-table .draft-player {{
                font-weight: 600;
                width: 42%;
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
