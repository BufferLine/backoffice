import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.schemas.account import AccountBalanceResponse, AccountCreate, AccountUpdate


async def create_account(
    db: AsyncSession,
    data: AccountCreate,
    created_by: Optional[uuid.UUID] = None,
) -> Account:
    account = Account(
        name=data.name,
        account_type=data.account_type,
        account_class=data.account_class,
        currency=data.currency,
        institution=data.institution,
        account_number=data.account_number,
        wallet_address=data.wallet_address,
        chain_id=data.chain_id,
        statement_source=data.statement_source,
        opening_balance=data.opening_balance,
        opening_balance_date=data.opening_balance_date,
        is_active=data.is_active,
        metadata_json=data.metadata_json,
        created_by=created_by,
    )
    db.add(account)
    await db.flush()
    return account


async def get_account(db: AsyncSession, account_id: uuid.UUID) -> Account:
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    return account


async def update_account(
    db: AsyncSession,
    account_id: uuid.UUID,
    data: AccountUpdate,
) -> Account:
    account = await get_account(db, account_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.flush()
    return account


async def list_accounts(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Account], int]:
    query = select(Account)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Account.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_balance(db: AsyncSession, account_id: uuid.UUID) -> AccountBalanceResponse:
    """Calculate account balance from confirmed journal lines (double-entry)."""
    account = await get_account(db, account_id)

    debit_result = await db.execute(
        select(func.coalesce(func.sum(JournalLine.debit), 0))
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.is_confirmed.is_(True),
        )
    )
    total_debit = Decimal(str(debit_result.scalar_one()))

    credit_result = await db.execute(
        select(func.coalesce(func.sum(JournalLine.credit), 0))
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalLine.account_id == account_id,
            JournalEntry.is_confirmed.is_(True),
        )
    )
    total_credit = Decimal(str(credit_result.scalar_one()))

    opening = Decimal(str(account.opening_balance))
    # For asset/expense accounts: balance = opening + debits - credits
    # For liability/equity/revenue accounts: balance = opening + credits - debits
    if account.account_class in ("liability", "equity", "revenue"):
        current = opening + total_credit - total_debit
    else:
        current = opening + total_debit - total_credit

    return AccountBalanceResponse(
        account_id=account.id,
        account_name=account.name,
        currency=account.currency,
        opening_balance=opening,
        confirmed_inflows=total_debit,
        confirmed_outflows=total_credit,
        current_balance=current,
    )


async def get_all_balances(db: AsyncSession) -> list[AccountBalanceResponse]:
    result = await db.execute(select(Account))
    accounts = list(result.scalars().all())
    balances = []
    for account in accounts:
        balance = await get_balance(db, account.id)
        balances.append(balance)
    return balances
