from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PaymentMethodCreate(BaseModel):
    name: str
    nickname: Optional[str] = None
    type: str
    currency: str
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_swift_code: Optional[str] = None
    wallet_address: Optional[str] = None
    chain_id: Optional[str] = None
    uen_number: Optional[str] = None
    is_default: Optional[bool] = False


class PaymentMethodUpdate(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    type: Optional[str] = None
    currency: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_swift_code: Optional[str] = None
    wallet_address: Optional[str] = None
    chain_id: Optional[str] = None
    uen_number: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class PaymentMethodResponse(BaseModel):
    id: UUID
    name: str
    nickname: Optional[str]
    type: str
    currency: str
    bank_name: Optional[str]
    bank_account_number: Optional[str]
    bank_swift_code: Optional[str]
    wallet_address: Optional[str]
    chain_id: Optional[str]
    uen_number: Optional[str]
    is_default: bool
    is_active: bool
    metadata_json: Optional[dict]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
