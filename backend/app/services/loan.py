import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loan import Loan
from app.models.payment_allocation import PaymentAllocation
from app.schemas.loan import LoanCreate, LoanUpdate
from app.services.audit import AuditService


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
