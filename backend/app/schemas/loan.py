from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LoanCreate(BaseModel):
    loan_type: str
    direction: str
    counterparty: str
    currency: str
    principal: Decimal
    interest_rate: Decimal = Decimal("0")
    interest_type: str = "simple"
    start_date: date
    maturity_date: Optional[date] = None
    description: Optional[str] = None


class LoanUpdate(BaseModel):
    loan_type: Optional[str] = None
    direction: Optional[str] = None
    counterparty: Optional[str] = None
    currency: Optional[str] = None
    principal: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    interest_type: Optional[str] = None
    start_date: Optional[date] = None
    maturity_date: Optional[date] = None
    description: Optional[str] = None


class LoanResponse(BaseModel):
    id: UUID
    loan_type: str
    direction: str
    counterparty: str
    currency: str
    principal: Decimal
    interest_rate: Decimal
    interest_type: str
    start_date: date
    maturity_date: Optional[date]
    status: str
    description: Optional[str]
    agreement_file_id: Optional[UUID] = None
    latest_statement_file_id: Optional[UUID] = None
    discharge_file_id: Optional[UUID] = None
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LoanListResponse(BaseModel):
    items: list[LoanResponse]
    total: int


class AllocationItem(BaseModel):
    id: UUID
    payment_id: UUID
    amount: Decimal
    notes: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class LoanBalanceResponse(BaseModel):
    principal: Decimal
    total_allocated: Decimal
    outstanding: Decimal
    allocations: list[AllocationItem]
