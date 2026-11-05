import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.journal import JournalEntry, JournalLine
from app.schemas.account import AccountBalanceResponse, AccountCreate, AccountUpdate


def _normalize_wallet_address(address: Optional[str]) -> Optional[str]:
    """EVM addresses are validated and lower-cased; other formats are kept as given."""
    if not address:
        return address
    address = address.strip()
    if address.lower().startswith("0x"):
        from app.services.onchain import normalize_address

        return normalize_address(address)
    return address


async def create_account(
    db: AsyncSession,
    data: AccountCreate,
    created_by: Optional[uuid.UUID] = None,
) -> Account:
    data = data.model_copy(update={"wallet_address": _normalize_wallet_address(data.wallet_address)})
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
    await db.refresh(account)
    if account.wallet_address or account.chain_id:
        from app.services.audit import AuditService

        await AuditService(db).log(
            action="account.wallet_set",
            entity_type="account",
            entity_id=account.id,
            actor_id=created_by,
            output_data={"wallet_address": account.wallet_address, "chain_id": account.chain_id},
        )
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
    actor_id: Optional[uuid.UUID] = None,
) -> Account:
    account = await get_account(db, account_id)
    changes = data.model_dump(exclude_unset=True)
    if "wallet_address" in changes:
        changes["wallet_address"] = _normalize_wallet_address(changes["wallet_address"])

    wallet_changes = {
        k: v for k, v in changes.items() if k in ("wallet_address", "chain_id") and v != getattr(account, k)
    }
    if wallet_changes:
        from app.models.payment import Payment

        # The address is evidence for receipts already verified against it: never rewrite it.
        used = (
            await db.execute(
                select(func.count(Payment.id)).where(
                    Payment.onchain_verification["to_address"].astext == (account.wallet_address or "").lower(),
                    Payment.onchain_verification["verified"].astext == "true",
                )
            )
        ).scalar_one()
        if used and account.wallet_address:
            raise ValueError(
                f"Account {account.name}'s wallet address is referenced by {used} verified receipt(s); "
                "create a new wallet account instead of changing it"
            )

    before = {k: getattr(account, k) for k in wallet_changes}
    for field, value in changes.items():
        setattr(account, field, value)
    await db.flush()
    await db.refresh(account)

    if wallet_changes:
        from app.services.audit import AuditService

        await AuditService(db).log(
            action="account.wallet_change",
            entity_type="account",
            entity_id=account.id,
            actor_id=actor_id,
            input_data=before,
            output_data=wallet_changes,
        )
    return account


async def list_accounts(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
    include_inactive: bool = False,
) -> tuple[list[Account], int]:
    query = select(Account)
    if not include_inactive:
        query = query.where(Account.is_active == True)  # noqa: E712

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
