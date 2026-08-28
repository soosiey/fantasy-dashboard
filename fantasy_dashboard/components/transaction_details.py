from html import escape
from textwrap import dedent

import streamlit as st

from fantasy_dashboard.transactions import TransactionDetailRow


# Format optional waiver bids as whole-dollar FAAB values where possible.
def _format_faab(faab: float | None) -> str:
    if faab is None:
        return "&mdash;"
    if faab.is_integer():
        return f"${faab:,.0f}"
    return f"${faab:,.2f}"


# Show one transaction's player movements in a compact modal table.
@st.dialog("Transaction Details", width="large")
def show_transaction_details(
    transaction_type: str,
    rows: list[TransactionDetailRow],
) -> None:
    st.subheader(transaction_type)
    if not rows:
        st.info("This transaction does not contain player movements.")
        return

    show_destination = transaction_type == "Trade"
    show_faab = transaction_type == "Waiver Add"
    table_rows = "".join(
        "<tr>"
        f'<td class="transaction-action">{escape(row.action)}</td>'
        f'<td class="transaction-player">{escape(row.player_name)}</td>'
        + (
            f'<td class="transaction-user">{escape(row.user)}</td>'
            if show_destination
            else ""
        )
        + (
            f'<td class="transaction-faab">{_format_faab(row.faab)}</td>'
            if show_faab
            else ""
        )
        + "</tr>"
        for row in rows
    )
    optional_header = (
        "<th>Traded To</th>"
        if show_destination
        else "<th>FAAB Spent</th>" if show_faab else ""
    )

    st.markdown(
        dedent(f"""
        <style>
            .transaction-details-table {{
                border-collapse: collapse;
                color: inherit;
                width: 100%;
            }}
            .transaction-details-table th,
            .transaction-details-table td {{
                border: none;
                padding: 0.65rem 0.8rem;
                text-align: left;
            }}
            .transaction-details-table th {{
                color: #808495;
                font-size: 0.78rem;
                text-transform: uppercase;
            }}
            .transaction-details-table tbody tr:nth-child(odd) {{
                background: rgba(128, 128, 128, 0.10);
            }}
            .transaction-details-table tbody tr:nth-child(even) {{
                background: rgba(128, 128, 128, 0.03);
            }}
            .transaction-details-table .transaction-action {{
                color: #a0a4b2;
                width: 22%;
            }}
            .transaction-details-table .transaction-player {{
                font-weight: 600;
            }}
            .transaction-details-table .transaction-faab {{
                font-variant-numeric: tabular-nums;
                text-align: right;
            }}
        </style>
        <table class="transaction-details-table">
            <thead>
                <tr><th>Action</th><th>Player</th>{optional_header}</tr>
            </thead>
            <tbody>{table_rows}</tbody>
        </table>
        """),
        unsafe_allow_html=True,
    )
