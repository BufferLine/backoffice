from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class Capability(str, Enum):
    SYNC_TRANSACTIONS = "sync_transactions"
    SYNC_BALANCE = "sync_balance"
    RECEIVE_WEBHOOK = "receive_webhook"
    CREATE_PAYMENT_LINK = "create_payment_link"
    INITIATE_TRANSFER = "initiate_transfer"
    VERIFY_PAYMENT = "verify_payment"
    PUSH_INVOICE = "push_invoice"
    PUSH_EXPENSE = "push_expense"
    FETCH_FX_RATE = "fetch_fx_rate"


@dataclass
class SyncedTransaction:
    source_tx_id: str
    tx_date: date
    amount: Decimal
    currency: str
    counterparty: str | None = None
    reference: str | None = None
    description: str | None = None
    raw_data: dict | None = None


@dataclass
class BalanceInfo:
    currency: str
    available_balance: Decimal
    pending_balance: Decimal | None = None
    as_of: datetime | None = None


@dataclass
class PaymentLinkResult:
    url: str
    provider_id: str
    expires_at: datetime | None = None


@dataclass
class TransferResult:
    provider_transfer_id: str
    status: str
    reference: str | None = None


@dataclass
class PaymentVerification:
    verified: bool
    amount: Decimal | None = None
    currency: str | None = None
    confirmations: int | None = None
    block_timestamp: datetime | None = None


@dataclass
class FXRate:
    sell_currency: str
    buy_currency: str
    rate: Decimal
    inverse_rate: Decimal | None = None
    valid_until: datetime | None = None
    raw_data: dict | None = None


@dataclass
class WebhookEvent:
    event_type: str
    event_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None
