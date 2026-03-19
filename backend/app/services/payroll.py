import calendar
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.jurisdiction import get_jurisdiction
from app.models.company import CompanySettings
from app.models.file import File
from app.models.payment import Payment
from app.models.payroll import Employee, PayrollDeduction, PayrollRun
from app.services.audit import AuditService
from app.services.file_storage import FileStorageService
from app.services.pdf import render_payslip_pdf
from app.state_machines import InvalidTransitionError
from app.state_machines.payroll import payroll_machine


async def _get_company_settings(db: AsyncSession) -> CompanySettings:
    result = await db.execute(select(CompanySettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        raise ValueError("Company settings not configured")
    return settings


async def create_employee(db: AsyncSession, data: dict, created_by: uuid.UUID) -> Employee:
    employee = Employee(
        name=data["name"],
        email=data.get("email"),
        base_salary=data["base_salary"],
        salary_currency=data["salary_currency"],
        start_date=data["start_date"],
        work_pass_type=data.get("work_pass_type"),
        tax_residency=data.get("tax_residency"),
        bank_details_json=data.get("bank_details_json"),
        status="active",
    )
    db.add(employee)
    await db.flush()
    return employee


async def update_employee(db: AsyncSession, employee_id: uuid.UUID, data: dict) -> Employee:
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if employee is None:
        return None

    for field in ("name", "email", "base_salary", "salary_currency", "end_date",
                  "work_pass_type", "tax_residency", "bank_details_json", "status"):
        if field in data and data[field] is not None:
            setattr(employee, field, data[field])

    await db.flush()
    return employee


async def create_payroll_run(
    db: AsyncSession,
    employee_id: uuid.UUID,
    month_str: str,
    start_date: Optional[date],
    end_date: Optional[date],
    created_by: uuid.UUID,
) -> PayrollRun:
    # Fetch employee
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if employee is None:
        raise ValueError(f"Employee {employee_id} not found")
    if employee.status != "active":
        raise ValueError(f"Employee {employee_id} is not active")

    # Parse month → first and last day
    year, month_num = map(int, month_str.split("-"))
    days_in_month = calendar.monthrange(year, month_num)[1]
    first_day = date(year, month_num, 1)
    last_day = date(year, month_num, days_in_month)

    # Calculate effective start/end dates
    effective_start = start_date if start_date is not None else max(employee.start_date, first_day)
    if end_date is not None:
        effective_end = end_date
    else:
        emp_end = employee.end_date if employee.end_date is not None else last_day
        effective_end = min(emp_end, last_day)

    # Clamp to month boundaries
    effective_start = max(effective_start, first_day)
    effective_end = min(effective_end, last_day)

    days_worked = (effective_end - effective_start).days + 1
    days_worked = max(0, days_worked)

    # Snapshot salary
    monthly_base_salary = Decimal(str(employee.base_salary))

    # Get jurisdiction
    company_settings = await _get_company_settings(db)
    jurisdiction_code = company_settings.jurisdiction or "SG"
    jurisdiction = get_jurisdiction(jurisdiction_code)

    # Calculate prorated gross salary
    prorated_gross = jurisdiction.prorate_salary(monthly_base_salary, days_worked, days_in_month)

    # Calculate deductions
    work_pass_type = employee.work_pass_type or "EP"
    raw_deductions = jurisdiction.calculate_deductions(prorated_gross, work_pass_type)

    # Calculate total employee-side deductions (exclude employer_cost items)
    total_deductions = Decimal("0")
    for d in raw_deductions:
        is_employer_cost = (d.metadata or {}).get("employer_cost", False)
        if not is_employer_cost:
            total_deductions += d.amount

    net_salary = prorated_gross - total_deductions

    # Create PayrollRun
    month_date = first_day  # store as first day of month
    run = PayrollRun(
        employee_id=employee_id,
        month=month_date,
        start_date=effective_start,
        end_date=effective_end,
        days_in_month=days_in_month,
        days_worked=days_worked,
        monthly_base_salary=monthly_base_salary,
        currency=employee.salary_currency,
        prorated_gross_salary=prorated_gross,
        total_deductions=total_deductions,
        net_salary=net_salary,
        status="draft",
        created_by=created_by,
    )
    db.add(run)
    await db.flush()

    # Create deduction records
    for idx, d in enumerate(raw_deductions):
        deduction = PayrollDeduction(
            payroll_run_id=run.id,
            deduction_type=d.deduction_type,
            description=d.description,
            amount=d.amount,
            rate=d.rate,
            cap_amount=d.cap_amount,
            metadata_json=d.metadata,
            sort_order=idx,
        )
        db.add(deduction)

    await db.flush()
    return run


async def _load_run_with_deductions(db: AsyncSession, run_id: uuid.UUID) -> Optional[PayrollRun]:
    result = await db.execute(
        select(PayrollRun)
        .where(PayrollRun.id == run_id)
        .options(
            selectinload(PayrollRun.deductions),
            selectinload(PayrollRun.employee),
        )
    )
    return result.scalar_one_or_none()


async def review_payroll(db: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID) -> PayrollRun:
    run = await _load_run_with_deductions(db, run_id)
    if run is None:
        return None

    new_state = payroll_machine.transition(run.status, "review")
    run.status = new_state
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action="payroll.review",
        entity_type="payroll_run",
        entity_id=run_id,
        actor_id=user_id,
        output_data={"status": new_state},
    )
    return run


async def finalize_payroll(
    db: AsyncSession,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> PayrollRun:
    run = await _load_run_with_deductions(db, run_id)
    if run is None:
        return None

    new_state = payroll_machine.transition(run.status, "finalize")
    run.status = new_state

    # Generate payslip PDF
    company_settings = await _get_company_settings(db)

    deductions_data = [
        {
            "type": d.deduction_type,
            "description": d.description,
            "amount": float(d.amount),
            "rate": float(d.rate) if d.rate is not None else None,
            "metadata": d.metadata_json or {},
        }
        for d in run.deductions
    ]

    pdf_data = {
        "company": {
            "legal_name": company_settings.legal_name or "",
            "uen": company_settings.uen or "",
            "address": company_settings.address or "",
        },
        "employee": {
            "name": run.employee.name,
            "email": run.employee.email or "",
            "work_pass_type": run.employee.work_pass_type or "",
        },
        "payroll": {
            "month": run.month.strftime("%B %Y"),
            "start_date": run.start_date.isoformat(),
            "end_date": run.end_date.isoformat(),
            "days_in_month": run.days_in_month,
            "days_worked": run.days_worked,
            "monthly_base_salary": float(run.monthly_base_salary),
            "currency": run.currency,
            "prorated_gross_salary": float(run.prorated_gross_salary),
            "total_deductions": float(run.total_deductions),
            "net_salary": float(run.net_salary),
        },
        "deductions": deductions_data,
    }

    pdf_bytes = render_payslip_pdf(pdf_data)

    filename = f"payslip_{run.employee.name.replace(' ', '_')}_{run.month.strftime('%Y-%m')}.pdf"
    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(pdf_bytes), filename, "application/pdf"
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=size,
        checksum_sha256=sha256,
        uploaded_by=user_id,
        linked_entity_type="payroll_run",
        linked_entity_id=run_id,
    )
    db.add(file_record)
    await db.flush()

    run.payslip_file_id = file_record.id
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action="payroll.finalize",
        entity_type="payroll_run",
        entity_id=run_id,
        actor_id=user_id,
        output_data={"status": new_state, "payslip_file_id": str(file_record.id)},
    )
    return run


async def mark_paid(
    db: AsyncSession,
    run_id: uuid.UUID,
    payment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> PayrollRun:
    run = await _load_run_with_deductions(db, run_id)
    if run is None:
        return None

    # Verify payment exists
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise ValueError(f"Payment {payment_id} not found")

    # Prevent payment reuse: reject if already linked to another payroll run
    existing_result = await db.execute(
        select(PayrollRun).where(
            PayrollRun.payment_id == payment_id,
            PayrollRun.id != run_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise ValueError(f"Payment {payment_id} is already linked to another payroll run")

    # Validate amount and currency match
    if Decimal(str(payment.amount)) != Decimal(str(run.net_salary)):
        raise ValueError(
            f"Payment amount {payment.amount} does not match payroll net salary {run.net_salary}"
        )
    if payment.currency != run.currency:
        raise ValueError(
            f"Payment currency {payment.currency} does not match payroll currency {run.currency}"
        )

    new_state = payroll_machine.transition(run.status, "mark_paid")
    run.status = new_state
    run.paid_at = datetime.now(tz=timezone.utc)
    run.payment_id = payment_id
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action="payroll.mark_paid",
        entity_type="payroll_run",
        entity_id=run_id,
        actor_id=user_id,
        output_data={"status": new_state, "payment_id": str(payment_id)},
    )
    return run


async def get_payroll_run(db: AsyncSession, run_id: uuid.UUID) -> Optional[PayrollRun]:
    return await _load_run_with_deductions(db, run_id)


async def list_payroll_runs(
    db: AsyncSession,
    month: Optional[str] = None,
    employee_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[PayrollRun], int]:
    query = (
        select(PayrollRun)
        .options(
            selectinload(PayrollRun.deductions),
            selectinload(PayrollRun.employee),
        )
        .order_by(PayrollRun.month.desc(), PayrollRun.created_at.desc())
    )
    count_query = select(func.count()).select_from(PayrollRun)

    if month is not None:
        year, month_num = map(int, month.split("-"))
        month_date = date(year, month_num, 1)
        query = query.where(PayrollRun.month == month_date)
        count_query = count_query.where(PayrollRun.month == month_date)

    if employee_id is not None:
        query = query.where(PayrollRun.employee_id == employee_id)
        count_query = count_query.where(PayrollRun.employee_id == employee_id)

    if status is not None:
        query = query.where(PayrollRun.status == status)
        count_query = count_query.where(PayrollRun.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    runs = list(result.scalars().all())

    return runs, total
