import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring_commitment import RecurringCommitment
from app.models.transaction import Transaction
from app.schemas.recurring_commitment import RecurringCommitmentCreate, RecurringCommitmentUpdate
from app.schemas.transaction import TransactionCreate


async def create_commitment(
    db: AsyncSession,
    data: RecurringCommitmentCreate,
    created_by: Optional[uuid.UUID] = None,
) -> RecurringCommitment:
    commitment = RecurringCommitment(
        name=data.name,
        category=data.category,
        account_id=data.account_id,
        currency=data.currency,
        expected_amount=data.expected_amount,
        frequency=data.frequency,
        day_of_period=data.day_of_period,
        vendor=data.vendor,
        description=data.description,
        is_active=data.is_active,
        next_due_date=data.next_due_date,
        tolerance_percent=data.tolerance_percent,
        metadata_json=data.metadata_json,
        created_by=created_by,
    )
    db.add(commitment)
    await db.flush()
    return commitment


async def get_commitment(db: AsyncSession, commitment_id: uuid.UUID) -> RecurringCommitment:
    result = await db.execute(
        select(RecurringCommitment).where(RecurringCommitment.id == commitment_id)
    )
    commitment = result.scalar_one_or_none()
    if commitment is None:
        raise ValueError(f"RecurringCommitment {commitment_id} not found")
    return commitment


async def update_commitment(
    db: AsyncSession,
    commitment_id: uuid.UUID,
    data: RecurringCommitmentUpdate,
) -> RecurringCommitment:
    commitment = await get_commitment(db, commitment_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(commitment, field, value)
    await db.flush()
    return commitment


async def list_commitments(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[RecurringCommitment], int]:
    query = select(RecurringCommitment)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(RecurringCommitment.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def deactivate_commitment(
    db: AsyncSession,
    commitment_id: uuid.UUID,
) -> RecurringCommitment:
    commitment = await get_commitment(db, commitment_id)
    commitment.is_active = False
    await db.flush()
    return commitment


def _applies_to_month(commitment: RecurringCommitment, year: int, month: int) -> bool:
    """Check if a commitment should generate a transaction in the given month."""
    if commitment.frequency == "monthly":
        return True
    elif commitment.frequency == "quarterly":
        return month in (1, 4, 7, 10)
    elif commitment.frequency == "yearly":
        if commitment.next_due_date:
            return commitment.next_due_date.month == month
        return month == 1
    return False


async def generate_pending_transactions(
    db: AsyncSession,
    month_str: str,
    created_by: Optional[uuid.UUID] = None,
) -> list[Transaction]:
    """
    Generate pending transactions for all active commitments for the given month.
    month_str format: "YYYY-MM"
    Skips if a transaction already exists for (recurring_commitment_id, period month).
    """
    from app.services.transaction import create_transaction

    year, month = int(month_str[:4]), int(month_str[5:7])

    result = await db.execute(
        select(RecurringCommitment).where(RecurringCommitment.is_active == True)  # noqa: E712
    )
    commitments = list(result.scalars().all())

    period_start = date(year, month, 1)
    if month == 12:
        period_end = date(year + 1, 1, 1)
    else:
        period_end = date(year, month + 1, 1)

    created_txs: list[Transaction] = []

    for commitment in commitments:
        if not _applies_to_month(commitment, year, month):
            continue

        # Skip if tx already exists for this commitment in this period
        existing_result = await db.execute(
            select(Transaction).where(
                Transaction.recurring_commitment_id == commitment.id,
                Transaction.tx_date >= period_start,
                Transaction.tx_date < period_end,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            continue

        # Determine tx_date from day_of_period
        day = commitment.day_of_period or 1
        # Clamp day to last day of month
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day = min(day, last_day)
        tx_date = date(year, month, day)

        if commitment.account_id is None:
            continue

        data = TransactionCreate(
            account_id=commitment.account_id,
            direction="out",
            amount=commitment.expected_amount,
            currency=commitment.currency,
            tx_date=tx_date,
            status="pending",
            category=commitment.category,
            counterparty=commitment.vendor,
            description=commitment.description,
            recurring_commitment_id=commitment.id,
        )
        tx = await create_transaction(db, data, created_by=created_by)
        created_txs.append(tx)

    return created_txs
