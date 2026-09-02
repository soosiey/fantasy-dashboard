from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fantasy_dashboard.models.transaction import TransactionModel


# Hold the display-ready values for the initial transactions table.
@dataclass(frozen=True, slots=True)
class TransactionRow:
    transaction_id: str
    transaction_type: str
    user: str
    created_at: int
    timestamp: str


# Hold one player movement rendered inside a transaction details dialog.
@dataclass(frozen=True, slots=True)
class TransactionDetailRow:
    action: str
    player_name: str
    user: str = ""
    faab: float | None = None


# Convert Sleeper's broad types and player movement into dashboard categories.
def _transaction_type_label(transaction: TransactionModel) -> str:
    if transaction.transaction_type == "trade":
        return "Trade"
    if transaction.transaction_type == "waiver":
        return "Waiver Add"
    if transaction.data.get("adds"):
        return "Add"
    if transaction.data.get("drops"):
        return "Drop"
    return "Add"


# Resolve each transaction's initiating Sleeper user for table display.
def _format_transaction_timestamp(created_at: int) -> str:
    if created_at <= 0:
        return "Unknown"
    timestamp = datetime.fromtimestamp(created_at / 1000, UTC).astimezone(
        ZoneInfo("America/New_York")
    )
    hour = timestamp.strftime("%I").lstrip("0") or "0"
    return (
        f"{timestamp:%b} {timestamp.day}, {timestamp.year} · "
        f"{hour}:{timestamp:%M %p}"
    )


def build_transaction_rows(
    transactions: list[TransactionModel],
    display_names_by_user_id: dict[str, str],
) -> list[TransactionRow]:
    return [
        TransactionRow(
            transaction_id=transaction.transaction_id,
            transaction_type=_transaction_type_label(transaction),
            user=display_names_by_user_id.get(transaction.creator_id, "Unknown User"),
            created_at=transaction.created_at,
            timestamp=_format_transaction_timestamp(transaction.created_at),
        )
        for transaction in sorted(
            transactions,
            key=lambda transaction: transaction.created_at,
            reverse=True,
        )
    ]


# Resolve a player ID to the cached catalog's current display name.
def _player_name(
    player_id: str,
    players: dict[str, dict],
) -> str:
    player = players.get(str(player_id)) or {}
    name = " ".join(
        part
        for part in (
            str(player.get("first_name") or "").strip(),
            str(player.get("last_name") or "").strip(),
        )
        if part
    )
    return name or str(player_id)


# Read an optional FAAB bid without allowing malformed provider data to fail.
def _waiver_bid(transaction: TransactionModel) -> float | None:
    settings = transaction.data.get("settings") or {}
    raw_bid = settings.get("waiver_bid") if isinstance(settings, dict) else None
    try:
        return float(raw_bid) if raw_bid not in (None, "") else None
    except (TypeError, ValueError):
        return None


# Build the player movements and destinations displayed by the details dialog.
def build_transaction_detail_rows(
    transaction: TransactionModel,
    players: dict[str, dict],
    display_names_by_roster_id: dict[int, str],
) -> list[TransactionDetailRow]:
    adds = transaction.data.get("adds") or {}
    drops = transaction.data.get("drops") or {}
    if not isinstance(adds, dict):
        adds = {}
    if not isinstance(drops, dict):
        drops = {}

    if transaction.transaction_type == "trade":
        return [
            TransactionDetailRow(
                action="Trade",
                player_name=_player_name(str(player_id), players),
                user=display_names_by_roster_id.get(int(roster_id), "Unknown User"),
            )
            for player_id, roster_id in adds.items()
        ]

    waiver_bid = _waiver_bid(transaction)
    rows = [
        TransactionDetailRow(
            action=(
                "Waiver Add" if transaction.transaction_type == "waiver" else "Add"
            ),
            player_name=_player_name(str(player_id), players),
            faab=waiver_bid,
        )
        for player_id in adds
    ]
    rows.extend(
        TransactionDetailRow(
            action="Drop",
            player_name=_player_name(str(player_id), players),
        )
        for player_id in drops
    )
    return rows
