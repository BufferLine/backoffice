from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    account_type: str
    currency: str
    institution: Optional[str] = None
    account_number: Optional[str] = None
    wallet_address: Optional[str] = None
    chain_id: Optional[str] = None
    statement_source: Optional[str] = None
    opening_balance: Decimal = Decimal("0")
    opening_balance_date: date
    is_active: bool = True
    metadata_json: Optional[dict] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    account_number: Optional[str] = None
    wallet_address: Optional[str] = None
    chain_id: Optional[str] = None
    statement_source: Optional[str] = None
    is_active: Optional[bool] = None
    metadata_json: Optional[dict] = None


class AccountResponse(BaseModel):
    id: UUID
    name: str
    account_type: str
    currency: str
    institution: Optional[str]
    account_number: Optional[str]
    wallet_address: Optional[str]
    chain_id: Optional[str]
    statement_source: Optional[str]
    opening_balance: Decimal
    opening_balance_date: date
    is_active: bool
    metadata_json: Optional[dict]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AccountBalanceResponse(BaseModel):
    account_id: UUID
    account_name: str
    currency: str
    opening_balance: Decimal
    confirmed_inflows: Decimal
    confirmed_outflows: Decimal
    current_balance: Decimal


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
