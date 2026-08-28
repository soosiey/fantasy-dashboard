from dataclasses import dataclass
from typing import Any


# Preserve the identifying fields and raw payload for one league transaction.
@dataclass(frozen=True, slots=True)
class TransactionModel:
    transaction_id: str
    transaction_type: str
    creator_id: str
    created_at: int
    data: dict[str, Any]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "TransactionModel":
        return cls(
            transaction_id=str(data.get("transaction_id") or ""),
            transaction_type=str(data.get("type") or "unknown"),
            creator_id=str(data.get("creator") or ""),
            created_at=int(data.get("created") or 0),
            data=dict(data),
        )

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "TransactionModel":
        return cls.from_json(data)


# Normalize transaction collections in newest-first display order.
@dataclass(frozen=True, slots=True)
class TransactionContainer:
    transactions: list[TransactionModel]

    @classmethod
    def from_api(cls, data: list[dict[str, Any]]) -> "TransactionContainer":
        return cls.from_models(
            [
                TransactionModel.from_api(transaction)
                for transaction in data
                if isinstance(transaction, dict)
            ]
        )

    @classmethod
    def from_models(
        cls, transactions: list[TransactionModel]
    ) -> "TransactionContainer":
        return cls(
            transactions=sorted(
                transactions,
                key=lambda transaction: transaction.created_at,
                reverse=True,
            )
        )
