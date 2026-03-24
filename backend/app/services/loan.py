import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import CompanySettings
from app.models.file import File
from app.models.loan import Loan
from app.models.payment import Payment
from app.models.payment_allocation import PaymentAllocation
from app.schemas.loan import LoanCreate, LoanUpdate
from app.services.audit import AuditService
from app.services.file_storage import FileStorageService

_LOAN_TYPE_DISPLAY = {
    "shareholder_loan": "Shareholder Loan",
    "director_loan": "Director Loan",
    "bank_loan": "Bank Loan",
    "intercompany_loan": "Intercompany Loan",
}

_DIRECTION_DISPLAY = {
    "inbound": "Borrowed (Company is Borrower)",
    "outbound": "Lent (Company is Lender)",
}


@dataclass(slots=True)
class LoanRepaymentEntry:
    """Normalized repayment entry across allocations and legacy direct links."""

    id: uuid.UUID
    payment_id: uuid.UUID
    amount: Decimal
    notes: str | None
    created_at: datetime
    payment_date: date | None
    payment_reference: str | None


async def create_loan(
    db: AsyncSession,
    data: LoanCreate,
    created_by: uuid.UUID,
) -> Loan:
    loan = Loan(
        loan_type=data.loan_type,
        direction=data.direction,
        counterparty=data.counterparty,
        currency=data.currency,
        principal=data.principal,
        interest_rate=data.interest_rate,
        interest_type=data.interest_type,
        start_date=data.start_date,
        maturity_date=data.maturity_date,
        description=data.description,
        status="active",
        created_by=created_by,
    )
    db.add(loan)
    await db.flush()
    await AuditService(db).log(
        action="loan.create",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=created_by,
        input_data=data.model_dump(mode="json"),
    )
    return loan


async def get_loan(db: AsyncSession, loan_id: uuid.UUID) -> Optional[Loan]:
    result = await db.execute(select(Loan).where(Loan.id == loan_id))
    return result.scalar_one_or_none()


async def list_loans(
    db: AsyncSession,
    status: Optional[str] = None,
    loan_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Loan], int]:
    query = select(Loan)

    if status:
        query = query.where(Loan.status == status)

    if loan_type:
        query = query.where(Loan.loan_type == loan_type)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Loan.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_loan(
    db: AsyncSession,
    loan: Loan,
    data: LoanUpdate,
) -> Loan:
    if loan.status != "active":
        raise ValueError(f"Cannot update loan with status '{loan.status}'")
    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(loan, key, value)
    await db.flush()
    return loan


async def get_loan_balance(
    db: AsyncSession,
    loan_id: uuid.UUID,
) -> tuple[Decimal, Decimal, Decimal, list[LoanRepaymentEntry]]:
    """Returns (principal, total_allocated, outstanding, allocations)."""
    loan_result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = loan_result.scalar_one_or_none()
    if loan is None:
        raise ValueError(f"Loan {loan_id} not found")

    allocations = await _get_loan_repayment_entries(db, loan_id)

    principal = Decimal(str(loan.principal))
    total_allocated = sum((entry.amount for entry in allocations), Decimal("0"))
    outstanding = principal - total_allocated

    return principal, total_allocated, outstanding, allocations


async def _get_loan_repayment_entries(
    db: AsyncSession,
    loan_id: uuid.UUID,
) -> list[LoanRepaymentEntry]:
    """Return repayment entries from both allocations and legacy payment links."""
    alloc_result = await db.execute(
        select(PaymentAllocation, Payment)
        .outerjoin(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.entity_type == "loan",
            PaymentAllocation.entity_id == loan_id,
        )
        .order_by(PaymentAllocation.created_at)
    )
    entries: list[LoanRepaymentEntry] = []
    seen_payment_ids: set[uuid.UUID] = set()

    for allocation, payment in alloc_result.all():
        seen_payment_ids.add(allocation.payment_id)
        entries.append(
            LoanRepaymentEntry(
                id=allocation.id,
                payment_id=allocation.payment_id,
                amount=Decimal(str(allocation.amount)),
                notes=allocation.notes,
                created_at=allocation.created_at,
                payment_date=payment.payment_date if payment else None,
                payment_reference=payment.bank_reference if payment else None,
            )
        )

    legacy_result = await db.execute(
        select(Payment)
        .where(
            Payment.related_entity_type == "loan",
            Payment.related_entity_id == loan_id,
        )
        .order_by(Payment.created_at)
    )
    for payment in legacy_result.scalars():
        if payment.id in seen_payment_ids:
            continue
        entries.append(
            LoanRepaymentEntry(
                id=payment.id,
                payment_id=payment.id,
                amount=Decimal(str(payment.amount)),
                notes=payment.notes,
                created_at=payment.created_at,
                payment_date=payment.payment_date,
                payment_reference=payment.bank_reference,
            )
        )

    return entries


async def mark_repaid(
    db: AsyncSession,
    loan: Loan,
    user_id: uuid.UUID,
) -> Loan:
    _, _, outstanding, _ = await get_loan_balance(db, loan.id)
    if outstanding != Decimal("0"):
        raise ValueError(f"Cannot mark loan as repaid: outstanding balance is {outstanding}")
    loan.status = "repaid"
    await db.flush()
    await AuditService(db).log(
        action="loan.mark_repaid",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=user_id,
        output_data={"status": "repaid"},
    )
    return loan


async def write_off_loan(
    db: AsyncSession,
    loan: Loan,
    user_id: uuid.UUID,
) -> Loan:
    loan.status = "written_off"
    await db.flush()
    await AuditService(db).log(
        action="loan.write_off",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=user_id,
        output_data={"status": "written_off"},
    )
    return loan


async def _load_company_and_branding(
    db: AsyncSession,
    file_storage: FileStorageService,
) -> tuple:
    """Load company settings and branding assets. Returns (company, company_data, stamp_bytes, stamp_mime, logo_bytes, logo_mime, theme)."""
    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()

    company_data = {}
    if company:
        company_data = {
            "legal_name": company.legal_name,
            "uen": company.uen,
            "address": company.address,
            "billing_email": company.billing_email,
        }

    stamp_bytes, stamp_mime, logo_bytes, logo_mime, theme = None, "image/png", None, "image/png", None
    if company:
        if company.stamp_file_id:
            stamp_file_result = await db.execute(select(File).where(File.id == company.stamp_file_id))
            stamp_file = stamp_file_result.scalar_one_or_none()
            if stamp_file:
                try:
                    stamp_bytes = file_storage.download(stamp_file.storage_key)
                    stamp_mime = stamp_file.mime_type or "image/png"
                except Exception:
                    pass
        if company.logo_file_id:
            logo_file_result = await db.execute(select(File).where(File.id == company.logo_file_id))
            logo_file = logo_file_result.scalar_one_or_none()
            if logo_file:
                try:
                    logo_bytes = file_storage.download(logo_file.storage_key)
                    logo_mime = logo_file.mime_type or "image/png"
                except Exception:
                    pass
        theme = {
            "primary_color": company.primary_color or "#1a56db",
            "accent_color": company.accent_color or "#374151",
            "font_family": company.font_family or "Helvetica, Arial, sans-serif",
        }

    return company, company_data, stamp_bytes, stamp_mime, logo_bytes, logo_mime, theme


def _build_loan_dict(loan: Loan) -> dict:
    return {
        "id": str(loan.id),
        "loan_type": loan.loan_type,
        "loan_type_display": _LOAN_TYPE_DISPLAY.get(loan.loan_type, loan.loan_type),
        "direction": loan.direction,
        "direction_display": _DIRECTION_DISPLAY.get(loan.direction, loan.direction),
        "counterparty": loan.counterparty,
        "currency": loan.currency,
        "principal": loan.principal,
        "interest_rate": loan.interest_rate,
        "interest_type": loan.interest_type,
        "start_date": loan.start_date,
        "maturity_date": loan.maturity_date,
        "description": loan.description,
    }


async def generate_loan_agreement_pdf(
    db: AsyncSession,
    loan: Loan,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> uuid.UUID:
    """Generate loan agreement PDF, upload to storage, return File ID. Immutable once generated."""
    from app.services.pdf import render_loan_agreement_pdf

    if loan.agreement_file_id is not None:
        raise ValueError("Agreement already generated — it is immutable")

    company, company_data, stamp_bytes, stamp_mime, logo_bytes, logo_mime, theme = (
        await _load_company_and_branding(db, file_storage)
    )
    if company is None or not company.legal_name:
        raise ValueError("Company settings must be configured before generating a loan agreement")

    _, total_repaid, outstanding, allocations = await get_loan_balance(db, loan.id)

    repayments = [
        {
            "date": entry.payment_date or entry.created_at.date(),
            "reference": entry.payment_reference,
            "amount": entry.amount,
            "notes": entry.notes,
        }
        for entry in allocations
    ]

    pdf_data = {
        "loan": _build_loan_dict(loan),
        "company": company_data,
        "repayments": repayments if repayments else None,
        "total_repaid": total_repaid,
        "outstanding": outstanding,
    }

    pdf_bytes = render_loan_agreement_pdf(
        pdf_data,
        stamp_bytes=stamp_bytes,
        stamp_mime=stamp_mime,
        logo_bytes=logo_bytes,
        logo_mime=logo_mime,
        theme=theme,
    )

    filename = f"loan-agreement-{str(loan.id)[:8]}.pdf"
    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(pdf_bytes), original_filename=filename, mime_type="application/pdf",
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=size,
        checksum_sha256=sha256,
        linked_entity_type="loan",
        linked_entity_id=loan.id,
    )
    db.add(file_record)
    await db.flush()

    loan.agreement_file_id = file_record.id
    loan.document_file_id = file_record.id  # backward compat
    await db.flush()

    await AuditService(db).log(
        action="loan.generate_pdf",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=user_id,
        output_data={"document_file_id": str(file_record.id)},
    )

    return file_record.id


async def generate_loan_statement_pdf(
    db: AsyncSession,
    loan: Loan,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> uuid.UUID:
    """Generate loan statement PDF, upload to storage, return File ID. Overwrites previous statement."""
    from app.services.pdf import render_loan_statement_pdf

    company, company_data, stamp_bytes, stamp_mime, logo_bytes, logo_mime, theme = (
        await _load_company_and_branding(db, file_storage)
    )
    if company is None or not company.legal_name:
        raise ValueError("Company settings must be configured before generating a loan statement")

    _, total_repaid, outstanding, allocations = await get_loan_balance(db, loan.id)

    repayments = [
        {
            "date": entry.payment_date or entry.created_at.date(),
            "reference": entry.payment_reference,
            "amount": entry.amount,
            "notes": entry.notes,
        }
        for entry in allocations
    ]

    pdf_data = {
        "loan": _build_loan_dict(loan),
        "company": company_data,
        "repayments": repayments if repayments else None,
        "total_repaid": total_repaid,
        "outstanding": outstanding,
        "statement_date": date.today(),
    }

    pdf_bytes = render_loan_statement_pdf(
        pdf_data,
        stamp_bytes=stamp_bytes,
        stamp_mime=stamp_mime,
        logo_bytes=logo_bytes,
        logo_mime=logo_mime,
        theme=theme,
    )

    filename = f"loan-statement-{str(loan.id)[:8]}.pdf"
    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(pdf_bytes), original_filename=filename, mime_type="application/pdf",
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=size,
        checksum_sha256=sha256,
        linked_entity_type="loan",
        linked_entity_id=loan.id,
    )
    db.add(file_record)
    await db.flush()

    loan.latest_statement_file_id = file_record.id
    await db.flush()

    await AuditService(db).log(
        action="loan.generate_statement",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=user_id,
        output_data={"document_file_id": str(file_record.id)},
    )

    return file_record.id


async def generate_loan_discharge_pdf(
    db: AsyncSession,
    loan: Loan,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> uuid.UUID:
    """Generate discharge letter PDF, upload to storage, return File ID. Immutable once generated."""
    from app.services.pdf import render_loan_discharge_pdf

    if loan.status != "repaid":
        raise ValueError(f"Cannot generate discharge letter: loan status is '{loan.status}', must be 'repaid'")

    _, _, outstanding, _ = await get_loan_balance(db, loan.id)
    if outstanding != Decimal("0"):
        raise ValueError(f"Cannot generate discharge letter: outstanding balance is {outstanding}")

    if loan.discharge_file_id is not None:
        raise ValueError("Discharge letter already generated — it is immutable")

    company, company_data, stamp_bytes, stamp_mime, logo_bytes, logo_mime, theme = (
        await _load_company_and_branding(db, file_storage)
    )
    if company is None or not company.legal_name:
        raise ValueError("Company settings must be configured before generating a discharge letter")

    _, total_repaid, _, allocations = await get_loan_balance(db, loan.id)

    repayments = [
        {
            "date": entry.payment_date or entry.created_at.date(),
            "reference": entry.payment_reference,
            "amount": entry.amount,
            "notes": entry.notes,
        }
        for entry in allocations
    ]

    pdf_data = {
        "loan": _build_loan_dict(loan),
        "company": company_data,
        "repayments": repayments if repayments else None,
        "total_repaid": total_repaid,
        "outstanding": Decimal("0"),
        "discharge_date": date.today(),
    }

    pdf_bytes = render_loan_discharge_pdf(
        pdf_data,
        stamp_bytes=stamp_bytes,
        stamp_mime=stamp_mime,
        logo_bytes=logo_bytes,
        logo_mime=logo_mime,
        theme=theme,
    )

    filename = f"loan-discharge-{str(loan.id)[:8]}.pdf"
    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(pdf_bytes), original_filename=filename, mime_type="application/pdf",
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=size,
        checksum_sha256=sha256,
        linked_entity_type="loan",
        linked_entity_id=loan.id,
    )
    db.add(file_record)
    await db.flush()

    loan.discharge_file_id = file_record.id
    await db.flush()

    await AuditService(db).log(
        action="loan.generate_discharge",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=user_id,
        output_data={"document_file_id": str(file_record.id)},
    )

    return file_record.id
