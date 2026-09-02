from fantasy_dashboard.models.transaction import TransactionContainer
from fantasy_dashboard.transactions import (
    build_transaction_detail_rows,
    build_transaction_rows,
)


# Transaction payloads should be normalized newest first with readable labels.
def test_transaction_rows_resolve_creator_names() -> None:
    transactions = TransactionContainer.from_api(
        [
            {
                "transaction_id": "older",
                "type": "free_agent",
                "creator": "user-1",
                "created": 100,
                "adds": {"player-1": 1},
            },
            {
                "transaction_id": "newer",
                "type": "trade",
                "creator": "user-2",
                "created": 200,
            },
        ]
    )

    rows = build_transaction_rows(
        transactions.transactions,
        {"user-1": "First User", "user-2": "Second User"},
    )

    assert [row.transaction_type for row in rows] == ["Trade", "Add"]
    assert [row.user for row in rows] == ["Second User", "First User"]
    assert [row.transaction_id for row in rows] == ["newer", "older"]
    assert [row.created_at for row in rows] == [200, 100]


def test_transaction_rows_sort_and_format_timestamps() -> None:
    transactions = TransactionContainer.from_api(
        [
            {
                "transaction_id": "new-year",
                "type": "free_agent",
                "creator": "user-1",
                "created": 1_767_243_600_000,
            },
            {
                "transaction_id": "unknown-time",
                "type": "free_agent",
                "creator": "user-1",
                "created": 0,
            },
        ]
    )

    rows = build_transaction_rows(list(reversed(transactions.transactions)), {})

    assert [row.transaction_id for row in rows] == ["new-year", "unknown-time"]
    assert rows[0].timestamp == "Jan 1, 2026 · 12:00 AM"
    assert rows[1].timestamp == "Unknown"


# Missing creator identities should not prevent the table from rendering.
def test_transaction_rows_handle_missing_users() -> None:
    transactions = TransactionContainer.from_api(
        [
            {
                "transaction_id": "waiver-1",
                "type": "waiver",
                "creator": "former-user",
                "created": 100,
            }
        ]
    )

    rows = build_transaction_rows(transactions.transactions, {})

    assert rows[0].transaction_type == "Waiver Add"
    assert rows[0].user == "Unknown User"


# Free-agent drops and waiver claims should use their specific categories.
def test_transaction_rows_classify_drop_and_waiver_add() -> None:
    transactions = TransactionContainer.from_api(
        [
            {
                "transaction_id": "drop-1",
                "type": "free_agent",
                "creator": "user-1",
                "created": 100,
                "drops": {"player-1": 1},
            },
            {
                "transaction_id": "waiver-1",
                "type": "waiver",
                "creator": "user-1",
                "created": 200,
                "adds": {"player-2": 1},
            },
        ]
    )

    rows = build_transaction_rows(
        transactions.transactions,
        {"user-1": "First User"},
    )

    assert [row.transaction_type for row in rows] == ["Waiver Add", "Drop"]


# Waiver details should include all movements and attach FAAB to the add.
def test_build_waiver_transaction_details() -> None:
    transaction = TransactionContainer.from_api(
        [
            {
                "transaction_id": "waiver-1",
                "type": "waiver",
                "creator": "user-1",
                "created": 100,
                "adds": {"player-1": 1},
                "drops": {"player-2": 1},
                "settings": {"waiver_bid": 17},
            }
        ]
    ).transactions[0]
    players = {
        "player-1": {"first_name": "Added", "last_name": "Player"},
        "player-2": {"first_name": "Dropped", "last_name": "Player"},
    }

    rows = build_transaction_detail_rows(transaction, players, {})

    assert [(row.action, row.player_name) for row in rows] == [
        ("Waiver Add", "Added Player"),
        ("Drop", "Dropped Player"),
    ]
    assert rows[0].faab == 17.0
    assert rows[1].faab is None


# Trade details should map each acquired player to the receiving roster owner.
def test_build_trade_transaction_details() -> None:
    transaction = TransactionContainer.from_api(
        [
            {
                "transaction_id": "trade-1",
                "type": "trade",
                "creator": "user-1",
                "created": 100,
                "adds": {"player-1": 2, "player-2": 1},
            }
        ]
    ).transactions[0]
    players = {
        "player-1": {"first_name": "First", "last_name": "Player"},
        "player-2": {"first_name": "Second", "last_name": "Player"},
    }

    rows = build_transaction_detail_rows(
        transaction,
        players,
        {1: "First User", 2: "Second User"},
    )

    assert [(row.player_name, row.user) for row in rows] == [
        ("First Player", "Second User"),
        ("Second Player", "First User"),
    ]
