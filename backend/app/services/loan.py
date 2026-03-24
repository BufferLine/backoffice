import io
import uuid
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
) -> tuple[Decimal, Decimal, Decimal, list[PaymentAllocation]]:
    """Returns (principal, total_allocated, outstanding, allocations)."""
    loan_result = await db.execute(select(Loan).where(Loan.id == loan_id))
    loan = loan_result.scalar_one_or_none()
    if loan is None:
        raise ValueError(f"Loan {loan_id} not found")

    alloc_result = await db.execute(
        select(PaymentAllocation).where(
            PaymentAllocation.entity_type == "loan",
            PaymentAllocation.entity_id == loan_id,
        )
    )
    allocations = list(alloc_result.scalars().all())

    principal = Decimal(str(loan.principal))
    total_allocated = sum((Decimal(str(a.amount)) for a in allocations), Decimal("0"))
    outstanding = principal - total_allocated

    return principal, total_allocated, outstanding, allocations


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


async def generate_loan_agreement_pdf(
    db: AsyncSession,
    loan: Loan,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> uuid.UUID:
    """Generate loan agreement PDF, upload to storage, return File ID."""
    from app.services.pdf import render_loan_agreement_pdf, _encode_image

    # Load company settings
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

    # Get repayment history via allocations
    _, total_repaid, outstanding, allocations = await get_loan_balance(db, loan.id)

    repayments = []
    for alloc in allocations:
        payment_result = await db.execute(select(Payment).where(Payment.id == alloc.payment_id))
        payment = payment_result.scalar_one_or_none()
        repayments.append({
            "date": payment.payment_date if payment else alloc.created_at.date(),
            "reference": payment.bank_reference if payment else None,
            "amount": alloc.amount,
            "notes": alloc.notes,
        })

    pdf_data = {
        "loan": {
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
        },
        "company": company_data,
        "repayments": repayments if repayments else None,
        "total_repaid": total_repaid,
        "outstanding": outstanding,
    }

    # Load branding
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

    # Link to loan
    loan.document_file_id = file_record.id
    await db.flush()

    await AuditService(db).log(
        action="loan.generate_pdf",
        entity_type="loan",
        entity_id=loan.id,
        actor_id=user_id,
        output_data={"document_file_id": str(file_record.id)},
    )

    return file_record.id
