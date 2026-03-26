from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class BankTransactionResponse(BaseModel):
    id: UUID
    source: str
    source_tx_id: str
    tx_date: date
    amount: Decimal
    currency: str
    counterparty: Optional[str]
    reference: Optional[str]
    description: Optional[str]
    matched_payment_id: Optional[UUID]
    match_status: str
    match_confidence: Optional[Decimal]
    raw_data_json: Optional[dict]
    statement_file_id: Optional[UUID]
    imported_at: datetime
    imported_by: Optional[UUID]

    model_config = {"from_attributes": True}


class BankTransactionListResponse(BaseModel):
    items: list[BankTransactionResponse]
    total: int


class BankTxMatchRequest(BaseModel):
    payment_id: UUID


class BankTxReconcileRequest(BaseModel):
    bank_account_id: UUID
    contra_account_id: UUID
    description: Optional[str] = None
    auto_confirm: bool = True


class AutoMatchResultItem(BaseModel):
    tx_id: UUID
    payment_id: UUID
    confidence: float


class AutoMatchResult(BaseModel):
    matched_count: int
    unmatched_count: int
    results: list[AutoMatchResultItem]
