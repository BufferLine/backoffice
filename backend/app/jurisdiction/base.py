from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class Deduction:
    deduction_type: str
    description: str
    amount: Decimal
    rate: Optional[Decimal] = None
    cap_amount: Optional[Decimal] = None
    metadata: Optional[dict] = None


@dataclass
class TaxResult:
    tax_rate: Decimal
    tax_amount: Decimal
    description: str
    is_inclusive: bool = False
    pre_tax_amount: Optional[Decimal] = None


class JurisdictionBase(ABC):
    @abstractmethod
    def calculate_deductions(self, gross_salary: Decimal, work_pass_type: str, **kwargs) -> list[Deduction]:
        """Calculate payroll deductions based on jurisdiction rules."""
        ...

    @abstractmethod
    def calculate_invoice_tax(self, subtotal: Decimal, gst_registered: bool, gst_rate: Decimal, tax_inclusive: bool = False) -> TaxResult:
        """Calculate tax on invoice subtotal."""
        ...

    @abstractmethod
    def prorate_salary(self, monthly_salary: Decimal, days_worked: int, days_in_month: int) -> Decimal:
        """Calculate prorated salary."""
        ...
