from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, model_validator


class JournalLineCreate(BaseModel):
    account_id: UUID
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    currency: str
    fx_rate_to_sgd: Optional[Decimal] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def check_debit_or_credit(self):
        if not ((self.debit > 0 and self.credit == 0) or (self.debit == 0 and self.credit > 0)):
            raise ValueError("Each line must have either debit > 0 or credit > 0, not both")
        return self


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[UUID] = None
    is_confirmed: bool = False
    lines: list[JournalLineCreate]

    @model_validator(mode="after")
    def check_balanced(self):
        if len(self.lines) < 2:
            raise ValueError("Journal entry must have at least 2 lines")

        currencies = {line.currency for line in self.lines}

        if len(currencies) == 1:
            # Single-currency: nominal balance check
            total_debit = sum(line.debit for line in self.lines)
            total_credit = sum(line.credit for line in self.lines)
            if total_debit != total_credit:
                raise ValueError(
                    f"Journal entry must balance: total debit ({total_debit}) != total credit ({total_credit})"
                )
        else:
            # Multi-currency: balance in SGD equivalent via fx_rate_to_sgd
            for line in self.lines:
                if line.fx_rate_to_sgd is None:
                    raise ValueError(
                        f"Multi-currency journal entry requires fx_rate_to_sgd on every line "
                        f"(missing for {line.currency} line)"
                    )
            total_debit_sgd = sum(line.debit * line.fx_rate_to_sgd for line in self.lines)
            total_credit_sgd = sum(line.credit * line.fx_rate_to_sgd for line in self.lines)
            # Allow small rounding tolerance for FX conversions
            diff = abs(total_debit_sgd - total_credit_sgd)
            if diff > Decimal("0.01"):
                raise ValueError(
                    f"Multi-currency journal entry must balance in SGD: "
                    f"total debit SGD ({total_debit_sgd}) != total credit SGD ({total_credit_sgd})"
                )
        return self


class JournalLineResponse(BaseModel):
    id: UUID
    journal_entry_id: UUID
    account_id: UUID
    debit: Decimal
    credit: Decimal
    currency: str
    fx_rate_to_sgd: Optional[Decimal]
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class JournalEntryResponse(BaseModel):
    id: UUID
    entry_date: date
    description: Optional[str]
    source_type: Optional[str]
    source_id: Optional[UUID]
    is_confirmed: bool
    confirmed_at: Optional[datetime]
    confirmed_by: Optional[UUID]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    lines: list[JournalLineResponse]

    model_config = {"from_attributes": True}


class JournalEntryListResponse(BaseModel):
    items: list[JournalEntryResponse]
    total: int


class TrialBalanceRow(BaseModel):
    account_id: UUID
    account_name: str
    account_class: Optional[str]
    currency: str
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal


class TrialBalanceResponse(BaseModel):
    as_of: date
    rows: list[TrialBalanceRow]
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool
