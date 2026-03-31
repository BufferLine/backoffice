from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class PaymentCreate(BaseModel):
    payment_type: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    payment_date: Optional[date] = None
    currency: str
    amount: Decimal
    fx_rate_to_sgd: Optional[Decimal] = None
    fx_rate_date: Optional[date] = None
    fx_rate_source: Optional[str] = None
    tx_hash: Optional[str] = None
    chain_id: Optional[str] = None
    reference_number: Optional[str] = None
    bank_reference: Optional[str] = None
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None


class PaymentResponse(BaseModel):
    id: UUID
    payment_type: str
    related_entity_type: Optional[str]
    related_entity_id: Optional[UUID]
    payment_date: Optional[date]
    currency: str
    amount: Decimal
    fx_rate_to_sgd: Optional[Decimal]
    fx_rate_date: Optional[date]
    fx_rate_source: Optional[str]
    sgd_value: Optional[Decimal]
    tx_hash: Optional[str]
    chain_id: Optional[str]
    reference_number: Optional[str]
    bank_reference: Optional[str]
    proof_file_id: Optional[UUID]
    idempotency_key: Optional[str]
    notes: Optional[str]
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int


class PaymentLinkRequest(BaseModel):
    related_entity_type: str
    related_entity_id: UUID


class PaymentPipelineRequest(BaseModel):
    """Request to create a payment from an entity with auto-proof and bank matching."""
    entity_type: Literal["payroll_run", "invoice", "loan"]
    entity_id: UUID
    payment_type: str = "bank_transfer"


class PaymentPipelineResponse(BaseModel):
    payment: PaymentResponse
    bank_match_tx_id: Optional[UUID] = None
    bank_match_confidence: Optional[float] = None
