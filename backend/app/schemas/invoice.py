from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# Client schemas
class ClientCreate(BaseModel):
    legal_name: str
    billing_email: Optional[str] = None
    billing_address: Optional[str] = None
    default_currency: Optional[str] = None
    payment_terms_days: Optional[int] = None
    preferred_payment_method: Optional[str] = None
    wallet_address: Optional[str] = None


class ClientUpdate(BaseModel):
    legal_name: Optional[str] = None
    billing_email: Optional[str] = None
    billing_address: Optional[str] = None
    default_currency: Optional[str] = None
    payment_terms_days: Optional[int] = None
    preferred_payment_method: Optional[str] = None
    wallet_address: Optional[str] = None
    is_active: Optional[bool] = None


class ClientResponse(BaseModel):
    id: UUID
    legal_name: str
    billing_email: Optional[str]
    billing_address: Optional[str]
    default_currency: Optional[str]
    payment_terms_days: Optional[int]
    preferred_payment_method: Optional[str]
    wallet_address: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Line item schemas
class LineItemCreate(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal


class LineItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None


class LineItemResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    sort_order: int

    model_config = {"from_attributes": True}


# Invoice schemas
class InvoiceCreate(BaseModel):
    client_id: UUID
    currency: str
    description: Optional[str] = None
    payment_method: Optional[str] = None
    wallet_address: Optional[str] = None


class InvoiceUpdate(BaseModel):
    description: Optional[str] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    wallet_address: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    client_id: UUID
    issue_date: Optional[date]
    due_date: Optional[date]
    currency: str
    subtotal_amount: Decimal
    tax_rate: Optional[Decimal]
    tax_amount: Decimal
    total_amount: Decimal
    status: str
    description: Optional[str]
    payment_method: Optional[str]
    wallet_address: Optional[str]
    line_items: list[LineItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    total: int


# Mark paid request
class MarkPaidRequest(BaseModel):
    payment_id: UUID


# Recurring invoice schemas
class RecurringRuleCreate(BaseModel):
    client_id: UUID
    frequency: str  # monthly, quarterly, yearly
    day_of_month: int
    currency: str
    line_items_json: list[dict]
    payment_method: Optional[str] = None
    description: Optional[str] = None


class RecurringRuleResponse(BaseModel):
    id: UUID
    client_id: UUID
    frequency: str
    day_of_month: int
    currency: str
    is_active: bool
    next_issue_date: Optional[date]
    created_at: datetime

    model_config = {"from_attributes": True}
