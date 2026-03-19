from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CompanySettingsResponse(BaseModel):
    id: UUID
    legal_name: Optional[str]
    uen: Optional[str]
    address: Optional[str]
    billing_email: Optional[str]
    bank_name: Optional[str]
    bank_account_number: Optional[str]
    bank_swift_code: Optional[str]
    logo_file_id: Optional[UUID]
    default_currency: Optional[str]
    default_payment_terms_days: int
    gst_registered: bool
    gst_rate: Optional[Decimal]
    jurisdiction: Optional[str]

    model_config = {"from_attributes": True}


class CompanySettingsUpdate(BaseModel):
    legal_name: Optional[str] = None
    uen: Optional[str] = None
    address: Optional[str] = None
    billing_email: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_swift_code: Optional[str] = None
    default_currency: Optional[str] = None
    default_payment_terms_days: Optional[int] = None
    gst_registered: Optional[bool] = None
    gst_rate: Optional[Decimal] = None
    jurisdiction: Optional[str] = None


class CurrencyResponse(BaseModel):
    code: str
    name: str
    symbol: str
    display_precision: int
    storage_precision: int
    is_crypto: bool
    chain_id: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class CurrencyCreate(BaseModel):
    code: str
    name: str
    symbol: str
    display_precision: int = 2
    storage_precision: int = 6
    is_crypto: bool = False
    chain_id: Optional[str] = None
