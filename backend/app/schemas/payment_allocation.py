from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AllocationCreate(BaseModel):
    entity_type: str
    entity_id: UUID
    amount: Decimal
    notes: Optional[str] = None


class AllocationResponse(BaseModel):
    id: UUID
    payment_id: UUID
    entity_type: str
    entity_id: UUID
    amount: Decimal
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AllocatePaymentRequest(BaseModel):
    allocations: list[AllocationCreate]


class AllocatePaymentResponse(BaseModel):
    payment_id: UUID
    allocations: list[AllocationResponse]
    unallocated_amount: Decimal
