import pandas as pd
import requests
import streamlit as st

from fantasy_dashboard.components.data_disclaimer import render_data_disclaimer
from fantasy_dashboard.components.transaction_details import (
    show_transaction_details,
)
from fantasy_dashboard.data import (
    clear_transaction_data,
    get_data_update,
    get_league_transactions,
    get_league_users,
    get_nfl_players,
    get_rosters,
)
from fantasy_dashboard.transactions import (
    build_transaction_detail_rows,
    build_transaction_rows,
)


# Resolve a dataframe button click to the transaction at the same row position.
def open_transaction_from_button(
    click_key: str,
    transaction_ids: list[str],
) -> None:
    click = st.session_state.get(click_key)
    if not click:
        return
    selected_row = int(click["row"])
    if 0 <= selected_row < len(transaction_ids):
        st.session_state["_selected_transaction_id"] = transaction_ids[
            selected_row
        ]

# Resolve league context consistently across direct links and page navigation.
league_id = st.query_params.get("league_id")
if league_id is not None:
    st.session_state["league_id"] = str(league_id)
else:
    league_id = st.session_state.get("league_id")

if league_id is None:
    st.warning("Select a league first.")
    st.switch_page("pages/leagues.py")

# Keep the force-refresh control compact and aligned with the page heading.
title_column, refresh_column = st.columns([8, 1], vertical_alignment="center")
with title_column:
    st.title("Transactions")
with refresh_column:
    force_refresh = st.button(
        "↻",
        key="refresh-transactions",
        help="Reload league transactions from Sleeper",
        width="content",
    )

if force_refresh:
    clear_transaction_data(league_id)
    st.rerun()

# Load every transaction week and resolve each initiating user for display.
try:
    transactions = get_league_transactions(league_id)
    league_users = get_league_users(league_id)
    rosters = get_rosters(league_id)
except (requests.RequestException, TypeError, ValueError) as error:
    st.warning(f"Transactions could not be loaded: {error}")
else:
    display_names_by_user_id = {
        user.user_id: user.display_name for user in league_users.users
    } if league_users is not None else {}
    rows = build_transaction_rows(
        transactions.transactions,
        display_names_by_user_id,
    )
    transaction_ids = [row.transaction_id for row in rows]

    st.caption(f"{len(rows):,} transactions")
    if not rows:
        st.info("No league transactions are available yet.")
    else:
        transaction_table = pd.DataFrame(
            [
                {
                    "Transaction Type": row.transaction_type,
                    "User": row.user,
                    "Details": "View",
                }
                for row in rows
            ]
        )
        st.dataframe(
            transaction_table,
            column_config={
                "Transaction Type": st.column_config.TextColumn(
                    "Transaction Type",
                    width="medium",
                ),
                "User": st.column_config.TextColumn("User", width="large"),
                "Details": st.column_config.ButtonColumn(
                    "Details",
                    width="small",
                    type="secondary",
                    on_click=open_transaction_from_button,
                    args=("transactions-click", transaction_ids),
                    key="transactions-click",
                ),
            },
            hide_index=True,
            width="stretch",
            height=700,
            key="transactions-table",
        )

        selected_transaction_id = st.session_state.pop(
            "_selected_transaction_id", None
        )
        if selected_transaction_id is not None:
            selected_transaction = next(
                (
                    transaction
                    for transaction in transactions.transactions
                    if transaction.transaction_id == selected_transaction_id
                ),
                None,
            )
            selected_row = next(
                (
                    row
                    for row in rows
                    if row.transaction_id == selected_transaction_id
                ),
                None,
            )
            if selected_transaction is not None and selected_row is not None:
                display_names_by_roster_id = {
                    roster.roster_id: display_names_by_user_id.get(
                        roster.user_id, "Unknown User"
                    )
                    for roster in rosters.rosters
                } if rosters is not None else {}
                detail_rows = build_transaction_detail_rows(
                    selected_transaction,
                    get_nfl_players(),
                    display_names_by_roster_id,
                )
                show_transaction_details(
                    selected_row.transaction_type,
                    detail_rows,
                )

    render_data_disclaimer(
        get_data_update("league_transactions", league_id)
    )

# Keep league and account navigation available below the transactions table.
with st.bottom:
    league_change = st.button("Switch Leagues")
    reset = st.button("Log Out")

if league_change:
    st.session_state.pop("league_id", None)
    if "league_id" in st.query_params:
        st.query_params.pop("league_id")
    st.switch_page("pages/leagues.py")
if reset:
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()
