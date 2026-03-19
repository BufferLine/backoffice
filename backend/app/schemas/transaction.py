from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

INFLOW_CATEGORIES = [
    "invoice_payment",
    "shareholder_loan",
    "share_capital",
    "intercompany_transfer_in",
    "refund_received",
    "interest",
    "grant",
    "other_inflow",
]

OUTFLOW_CATEGORIES = [
    "salary",
    "expense_payment",
    "subscription",
    "rent",
    "tax_payment",
    "intercompany_transfer_out",
    "refund_sent",
    "bank_fee",
    "other_outflow",
]

ALL_CATEGORIES = INFLOW_CATEGORIES + OUTFLOW_CATEGORIES


class TransactionCreate(BaseModel):
    account_id: UUID
    direction: str  # "in" or "out"
    amount: Decimal
    currency: str
    tx_date: date
    status: str = "pending"
    category: str
    counterparty: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    payment_id: Optional[UUID] = None
    bank_transaction_id: Optional[UUID] = None
    recurring_commitment_id: Optional[UUID] = None
    fx_rate_to_sgd: Optional[Decimal] = None
    sgd_value: Optional[Decimal] = None
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class TransactionUpdate(BaseModel):
    amount: Optional[Decimal] = None
    tx_date: Optional[date] = None
    category: Optional[str] = None
    counterparty: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    fx_rate_to_sgd: Optional[Decimal] = None
    sgd_value: Optional[Decimal] = None
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class TransactionResponse(BaseModel):
    id: UUID
    account_id: UUID
    direction: str
    amount: Decimal
    currency: str
    tx_date: date
    status: str
    category: str
    counterparty: Optional[str]
    description: Optional[str]
    reference: Optional[str]
    payment_id: Optional[UUID]
    bank_transaction_id: Optional[UUID]
    recurring_commitment_id: Optional[UUID]
    fx_rate_to_sgd: Optional[Decimal]
    sgd_value: Optional[Decimal]
    notes: Optional[str]
    metadata_json: Optional[dict]
    confirmed_at: Optional[datetime]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
