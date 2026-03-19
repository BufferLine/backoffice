from pydantic import BaseModel
from datetime import date, datetime
from uuid import UUID
from typing import Optional


class ExportValidationResult(BaseModel):
    month: str
    is_complete: bool
    invoices_total: int
    invoices_issued_or_paid: int
    invoices_draft: int
    payroll_total: int
    payroll_finalized_or_paid: int
    payroll_pending: int
    expenses_total: int
    expenses_confirmed: int
    expenses_draft: int
    missing_evidence: list[dict]  # [{entity_type, entity_id, description}]


class ExportPackResponse(BaseModel):
    id: UUID
    month: date
    version: int
    generated_at: Optional[datetime]
    status: str
    notes: Optional[str]
    validation_summary_json: Optional[dict]
    created_by: Optional[UUID]
    model_config = {"from_attributes": True}


class ExportListResponse(BaseModel):
    items: list[ExportPackResponse]
    total: int


class MonthEndRequest(BaseModel):
    month: str  # YYYY-MM format
    force: bool = False


class AutomationResult(BaseModel):
    report_type: str  # daily, weekly, monthly
    generated_at: datetime
    items: list[dict]
    summary: dict
