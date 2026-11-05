import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.schemas.journal import JournalEntryCreate, TrialBalanceResponse, TrialBalanceRow


async def create_journal_entry(
    db: AsyncSession,
    data: JournalEntryCreate,
    created_by: Optional[uuid.UUID] = None,
) -> JournalEntry:
    entry = JournalEntry(
        entry_date=data.entry_date,
        description=data.description,
        source_type=data.source_type,
        source_id=data.source_id,
        is_confirmed=data.is_confirmed,
        confirmed_at=datetime.now() if data.is_confirmed else None,
        confirmed_by=created_by if data.is_confirmed else None,
        created_by=created_by,
    )
    db.add(entry)
    await db.flush()

    for line_data in data.lines:
        line = JournalLine(
            journal_entry_id=entry.id,
            account_id=line_data.account_id,
            debit=line_data.debit,
            credit=line_data.credit,
            currency=line_data.currency,
            fx_rate_to_sgd=line_data.fx_rate_to_sgd,
            description=line_data.description,
        )
        db.add(line)

    await db.flush()
    await db.refresh(entry)
    return entry


async def get_journal_entry(db: AsyncSession, entry_id: uuid.UUID) -> JournalEntry:
    result = await db.execute(
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(JournalEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise ValueError(f"Journal entry {entry_id} not found")
    return entry


async def list_journal_entries(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    confirmed_only: Optional[bool] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> tuple[list[JournalEntry], int]:
    query = select(JournalEntry).options(selectinload(JournalEntry.lines))

    if confirmed_only is True:
        query = query.where(JournalEntry.is_confirmed.is_(True))
    elif confirmed_only is False:
        query = query.where(JournalEntry.is_confirmed.is_(False))

    if from_date:
        query = query.where(JournalEntry.entry_date >= from_date)
    if to_date:
        query = query.where(JournalEntry.entry_date <= to_date)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().unique().all())

    return items, total


async def confirm_journal_entry(
    db: AsyncSession,
    entry_id: uuid.UUID,
    confirmed_by: Optional[uuid.UUID] = None,
) -> JournalEntry:
    entry = await get_journal_entry(db, entry_id)
    if entry.is_confirmed:
        return entry
    entry.is_confirmed = True
    entry.confirmed_at = datetime.now()
    entry.confirmed_by = confirmed_by
    await db.flush()
    await db.refresh(entry)
    return entry


async def delete_journal_entry(db: AsyncSession, entry_id: uuid.UUID) -> None:
    entry = await get_journal_entry(db, entry_id)
    if entry.is_confirmed:
        raise ValueError("Cannot delete a confirmed journal entry")
    await db.delete(entry)
    await db.flush()


async def get_trial_balance(
    db: AsyncSession,
    as_of: Optional[date] = None,
    confirmed_only: bool = True,
) -> TrialBalanceResponse:
    if as_of is None:
        as_of = date.today()

    query = (
        select(
            JournalLine.account_id,
            Account.name.label("account_name"),
            Account.account_class,
            Account.currency,
            func.coalesce(func.sum(JournalLine.debit), 0).label("total_debit"),
            func.coalesce(func.sum(JournalLine.credit), 0).label("total_credit"),
            # SGD equivalent (functional currency). Unrated lines come from single-currency
            # entries, which balance nominally, so a rate of 1 keeps them neutral.
            func.coalesce(func.sum(JournalLine.debit * func.coalesce(JournalLine.fx_rate_to_sgd, 1)), 0).label("debit_sgd"),
            func.coalesce(func.sum(JournalLine.credit * func.coalesce(JournalLine.fx_rate_to_sgd, 1)), 0).label("credit_sgd"),
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(JournalEntry.entry_date <= as_of)
    )

    if confirmed_only:
        query = query.where(JournalEntry.is_confirmed.is_(True))

    query = query.group_by(
        JournalLine.account_id, Account.name, Account.account_class, Account.currency
    )
    query = query.order_by(Account.account_class, Account.name)

    result = await db.execute(query)
    rows_raw = result.all()

    rows = []
    grand_debit = Decimal(0)
    grand_credit = Decimal(0)
    grand_debit_sgd = Decimal(0)
    grand_credit_sgd = Decimal(0)

    for row in rows_raw:
        td = Decimal(str(row.total_debit))
        tc = Decimal(str(row.total_credit))
        ds = Decimal(str(row.debit_sgd))
        cs = Decimal(str(row.credit_sgd))
        grand_debit += td
        grand_credit += tc
        grand_debit_sgd += ds
        grand_credit_sgd += cs
        rows.append(
            TrialBalanceRow(
                account_id=row.account_id,
                account_name=row.account_name,
                account_class=row.account_class,
                currency=row.currency,
                total_debit=td,
                total_credit=tc,
                balance=td - tc,
                balance_sgd=(ds - cs).quantize(Decimal("0.01")),
            )
        )

    # Multi-currency entries are validated to balance in SGD within 0.01 each,
    # so allow that much per such entry in the grand total.
    mc_entries = select(JournalLine.journal_entry_id).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).where(JournalEntry.entry_date <= as_of)
    if confirmed_only:
        mc_entries = mc_entries.where(JournalEntry.is_confirmed.is_(True))
    mc_entries = mc_entries.group_by(JournalLine.journal_entry_id).having(
        func.count(func.distinct(JournalLine.currency)) > 1
    )
    mc_count = (await db.execute(select(func.count()).select_from(mc_entries.subquery()))).scalar_one()
    tolerance = Decimal("0.01") * mc_count

    return TrialBalanceResponse(
        as_of=as_of,
        rows=rows,
        total_debit=grand_debit,
        total_credit=grand_credit,
        total_debit_sgd=grand_debit_sgd.quantize(Decimal("0.01")),
        total_credit_sgd=grand_credit_sgd.quantize(Decimal("0.01")),
        is_balanced=abs(grand_debit_sgd - grand_credit_sgd) <= tolerance,
    )


async def get_account_ledger(
    db: AsyncSession,
    account_id: uuid.UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    confirmed_only: bool = True,
) -> list[dict]:
    query = (
        select(
            JournalLine,
            JournalEntry.entry_date,
            JournalEntry.description.label("entry_description"),
            JournalEntry.source_type,
            JournalEntry.is_confirmed,
        )
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(JournalLine.account_id == account_id)
    )

    if confirmed_only:
        query = query.where(JournalEntry.is_confirmed.is_(True))
    if from_date:
        query = query.where(JournalEntry.entry_date >= from_date)
    if to_date:
        query = query.where(JournalEntry.entry_date <= to_date)

    query = query.order_by(JournalEntry.entry_date, JournalEntry.created_at)

    result = await db.execute(query)
    rows = result.all()

    ledger = []
    running_balance = Decimal(0)
    for row in rows:
        line = row[0]
        debit = Decimal(str(line.debit))
        credit = Decimal(str(line.credit))
        running_balance += debit - credit
        ledger.append({
            "line_id": line.id,
            "journal_entry_id": line.journal_entry_id,
            "entry_date": row.entry_date,
            "description": line.description or row.entry_description,
            "source_type": row.source_type,
            "debit": debit,
            "credit": credit,
            "balance": running_balance,
            "is_confirmed": row.is_confirmed,
        })

    return ledger
