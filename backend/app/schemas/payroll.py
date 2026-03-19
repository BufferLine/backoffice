from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, model_validator


# Employee schemas
class EmployeeCreate(BaseModel):
    name: str
    email: Optional[str] = None
    base_salary: Decimal
    salary_currency: str
    start_date: date
    work_pass_type: Optional[str] = None
    tax_residency: Optional[str] = None
    bank_details_json: Optional[dict] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    base_salary: Optional[Decimal] = None
    salary_currency: Optional[str] = None
    end_date: Optional[date] = None
    work_pass_type: Optional[str] = None
    tax_residency: Optional[str] = None
    bank_details_json: Optional[dict] = None
    status: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: UUID
    name: str
    email: Optional[str]
    base_salary: Decimal
    salary_currency: str
    start_date: date
    end_date: Optional[date]
    work_pass_type: Optional[str]
    tax_residency: Optional[str]
    bank_details_json: Optional[dict]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Payroll deduction schema
class PayrollDeductionResponse(BaseModel):
    id: UUID
    payroll_run_id: UUID
    deduction_type: str
    description: Optional[str]
    amount: Decimal
    rate: Optional[Decimal]
    cap_amount: Optional[Decimal]
    metadata_json: Optional[dict]
    sort_order: int

    model_config = {"from_attributes": True}


# Payroll run schemas
class PayrollRunCreate(BaseModel):
    employee_id: UUID
    month: str  # "YYYY-MM"
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class PayrollRunResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employee_name: str
    month: date
    start_date: date
    end_date: date
    days_in_month: int
    days_worked: int
    monthly_base_salary: Decimal
    currency: str
    prorated_gross_salary: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    status: str
    payslip_file_id: Optional[UUID]
    paid_at: Optional[datetime]
    payment_id: Optional[UUID]
    deductions: list[PayrollDeductionResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_employee_name(cls, data: Any) -> Any:
        """When built from an ORM PayrollRun, pull employee.name into employee_name."""
        if not isinstance(data, dict):
            # ORM object path
            employee = getattr(data, "employee", None)
            if employee is not None:
                # Convert to dict to allow setting employee_name
                return {
                    "id": data.id,
                    "employee_id": data.employee_id,
                    "employee_name": employee.name,
                    "month": data.month,
                    "start_date": data.start_date,
                    "end_date": data.end_date,
                    "days_in_month": data.days_in_month,
                    "days_worked": data.days_worked,
                    "monthly_base_salary": data.monthly_base_salary,
                    "currency": data.currency,
                    "prorated_gross_salary": data.prorated_gross_salary,
                    "total_deductions": data.total_deductions,
                    "net_salary": data.net_salary,
                    "status": data.status,
                    "payslip_file_id": data.payslip_file_id,
                    "paid_at": data.paid_at,
                    "payment_id": data.payment_id,
                    "deductions": data.deductions,
                    "created_at": data.created_at,
                    "updated_at": data.updated_at,
                }
        return data


class PayrollListResponse(BaseModel):
    items: list[PayrollRunResponse]
    total: int


class PayrollMarkPaidRequest(BaseModel):
    payment_id: UUID
