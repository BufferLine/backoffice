from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, model_validator


class FxConversionCreate(BaseModel):
    conversion_date: date
    sell_currency: str
    sell_amount: Decimal
    buy_currency: str
    buy_amount: Decimal
    sell_account_id: UUID
    buy_account_id: UUID
    provider: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def check_different_currencies(self):
        if self.sell_currency == self.buy_currency:
            raise ValueError("sell_currency and buy_currency must be different")
        return self


class FxConversionResponse(BaseModel):
    id: UUID
    conversion_date: date
    sell_currency: str
    sell_amount: Decimal
    buy_currency: str
    buy_amount: Decimal
    fx_rate: Decimal
    sell_account_id: UUID
    buy_account_id: UUID
    journal_entry_id: Optional[UUID]
    provider: Optional[str]
    reference: Optional[str]
    notes: Optional[str]
    created_by: Optional[UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class FxConversionListResponse(BaseModel):
    items: list[FxConversionResponse]
    total: int
