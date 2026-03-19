from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RecurringCommitmentCreate(BaseModel):
    name: str
    category: str
    account_id: Optional[UUID] = None
    currency: str
    expected_amount: Decimal
    frequency: str  # "monthly", "quarterly", "yearly"
    day_of_period: Optional[int] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    next_due_date: Optional[date] = None
    tolerance_percent: Decimal = Decimal("10.00")
    metadata_json: Optional[dict] = None


class RecurringCommitmentUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[UUID] = None
    expected_amount: Optional[Decimal] = None
    frequency: Optional[str] = None
    day_of_period: Optional[int] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    next_due_date: Optional[date] = None
    tolerance_percent: Optional[Decimal] = None
    metadata_json: Optional[dict] = None


class RecurringCommitmentResponse(BaseModel):
    id: UUID
    name: str
    category: str
    account_id: Optional[UUID]
    currency: str
    expected_amount: Decimal
    frequency: str
    day_of_period: Optional[int]
    vendor: Optional[str]
    description: Optional[str]
    is_active: bool
    next_due_date: Optional[date]
    last_transaction_id: Optional[UUID]
    tolerance_percent: Decimal
    metadata_json: Optional[dict]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecurringCommitmentListResponse(BaseModel):
    items: list[RecurringCommitmentResponse]
    total: int
