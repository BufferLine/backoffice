from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ExpenseCreate(BaseModel):
    expense_date: date
    vendor: Optional[str] = None
    category: Optional[str] = None
    currency: str
    amount: Decimal
    payment_method: Optional[str] = None
    reimbursable: Optional[bool] = False
    notes: Optional[str] = None


class ExpenseUpdate(BaseModel):
    vendor: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    reimbursable: Optional[bool] = None
    notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: UUID
    expense_date: date
    vendor: Optional[str]
    category: Optional[str]
    currency: str
    amount: Decimal
    payment_method: Optional[str]
    reimbursable: bool
    status: str
    notes: Optional[str]
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    total: int
