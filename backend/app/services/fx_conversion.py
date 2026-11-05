import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.bank_transaction import BankTransaction
from app.models.fx_conversion import FxConversion
from app.schemas.fx_conversion import FxConversionCreate
from app.schemas.journal import JournalEntryCreate, JournalLineCreate
from app.services import ledger
from app.services.audit import AuditService
from app.services.journal import create_journal_entry


async def record_fx_conversion(
    db: AsyncSession,
    data: FxConversionCreate,
    created_by: uuid.UUID,
) -> FxConversion:
    """Record an FX conversion and auto-create a balanced journal entry (SGD functional).

    - Buying a foreign currency/stablecoin with SGD: the bought side is recorded at
      the conversion rate (its cost). No gain or loss.
    - Selling a foreign currency/stablecoin for SGD (e.g. a USDC off-ramp): when the
      sold account has a rated carrying balance and an FX gain/loss account is mapped,
      the sold side leaves at its weighted-average carrying rate and the difference to
      the SGD actually received is booked as realised FX gain/loss. Otherwise the
      conversion rate is used for both sides (no gain/loss), as before.

    If ``bank_transaction_id`` is given, that bank deposit is the SGD landing of this
    conversion: it is validated against the bought side and marked reconciled, so it is
    not booked a second time by bank reconciliation.
    """
    sell_account = await _get_account(db, data.sell_account_id)
    buy_account = await _get_account(db, data.buy_account_id)

    if sell_account.currency != data.sell_currency:
        raise ValueError(
            f"Sell account currency ({sell_account.currency}) "
            f"does not match sell_currency ({data.sell_currency})"
        )
    if buy_account.currency != data.buy_currency:
        raise ValueError(
            f"Buy account currency ({buy_account.currency}) "
            f"does not match buy_currency ({data.buy_currency})"
        )

    # Require at least one side to be SGD (functional currency)
    if data.sell_currency != "SGD" and data.buy_currency != "SGD":
        raise ValueError(
            "At least one side of the FX conversion must be SGD (functional currency). "
            "For non-SGD pairs, record two separate conversions via SGD."
        )

    bank_tx = None
    if data.bank_transaction_id is not None:
        bank_tx = await _get_landing_bank_transaction(db, data)

    # FX rate: how much sell_currency per 1 buy_currency
    fx_rate = Decimal(str(data.sell_amount)) / Decimal(str(data.buy_amount))

    fx_line = None
    if data.sell_currency == "SGD":
        sell_fx_rate = Decimal("1")
        buy_fx_rate = fx_rate  # SGD per 1 buy_currency (cost)
    else:
        buy_fx_rate = Decimal("1")
        sell_fx_rate = Decimal("1") / fx_rate  # SGD per 1 sell_currency
        mapping = await ledger.get_ledger_accounts(db)
        carrying = await ledger.carrying_rate_to_sgd(db, data.sell_account_id, data.conversion_date)
        # Without an accrual ledger mapping, keep the legacy behaviour (conversion rate, no gain/loss).
        if carrying is not None and mapping.configured:
            sell_fx_rate = carrying
            diff = Decimal(str(data.buy_amount)) - Decimal(str(data.sell_amount)) * carrying
            if ledger.q_sgd(diff) != 0:
                fx_line = ledger.fx_difference_line(
                    diff,
                    mapping.require_fx_gain_loss(),
                    f"{data.sell_currency} {data.sell_amount:,.2f} sold at {fx_rate:.6f} vs carrying {carrying}",
                )

    lines = [
        JournalLineCreate(
            account_id=data.buy_account_id,
            debit=data.buy_amount,
            credit=Decimal("0"),
            currency=data.buy_currency,
            fx_rate_to_sgd=buy_fx_rate,
            description=f"FX buy {data.buy_currency} {data.buy_amount:,.2f}",
        ),
        JournalLineCreate(
            account_id=data.sell_account_id,
            debit=Decimal("0"),
            credit=data.sell_amount,
            currency=data.sell_currency,
            fx_rate_to_sgd=sell_fx_rate,
            description=f"FX sell {data.sell_currency} {data.sell_amount:,.2f}",
        ),
    ]
    if fx_line is not None:
        lines.append(fx_line)

    conversion = FxConversion(
        conversion_date=data.conversion_date,
        sell_currency=data.sell_currency,
        sell_amount=data.sell_amount,
        buy_currency=data.buy_currency,
        buy_amount=data.buy_amount,
        fx_rate=fx_rate,
        sell_account_id=data.sell_account_id,
        buy_account_id=data.buy_account_id,
        bank_transaction_id=bank_tx.id if bank_tx is not None else None,
        provider=data.provider,
        reference=data.reference,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(conversion)
    await db.flush()

    journal_data = JournalEntryCreate(
        entry_date=data.conversion_date,
        description=(
            f"FX conversion: {data.sell_currency} {data.sell_amount:,.2f} → "
            f"{data.buy_currency} {data.buy_amount:,.2f} @ {fx_rate:.6f}"
        ),
        source_type="fx_conversion",
        source_id=conversion.id,
        is_confirmed=True,
        lines=lines,
    )
    journal_entry = await create_journal_entry(db, journal_data, created_by=created_by)
    conversion.journal_entry_id = journal_entry.id

    if bank_tx is not None:
        bank_tx.match_status = "reconciled"
        bank_tx.account_id = data.buy_account_id
    await db.flush()

    await AuditService(db).log(
        action="fx_conversion.record",
        entity_type="fx_conversion",
        entity_id=conversion.id,
        actor_id=created_by,
        input_data={
            "sell": f"{data.sell_currency} {data.sell_amount}",
            "buy": f"{data.buy_currency} {data.buy_amount}",
            "fx_rate": str(fx_rate),
            "provider": data.provider,
            "bank_transaction_id": str(bank_tx.id) if bank_tx is not None else None,
            "fx_gain_loss_sgd": str(fx_line.credit - fx_line.debit) if fx_line is not None else None,
        },
    )
    return conversion


async def _get_landing_bank_transaction(db: AsyncSession, data: FxConversionCreate) -> BankTransaction:
    """The bank deposit the bought currency landed as; must match the bought side exactly."""
    tx = (
        await db.execute(select(BankTransaction).where(BankTransaction.id == data.bank_transaction_id))
    ).scalar_one_or_none()
    if tx is None:
        raise ValueError(f"Bank transaction {data.bank_transaction_id} not found")
    if tx.match_status == "reconciled":
        raise ValueError(f"Bank transaction {tx.id} is already reconciled")
    if tx.currency != data.buy_currency:
        raise ValueError(f"Bank transaction currency {tx.currency} does not match buy_currency {data.buy_currency}")
    if Decimal(str(tx.amount)) != Decimal(str(data.buy_amount)):
        raise ValueError(
            f"Bank transaction amount {tx.amount} does not match buy_amount {data.buy_amount}"
        )
    if tx.account_id is not None and tx.account_id != data.buy_account_id:
        raise ValueError(f"Bank transaction {tx.id} belongs to a different account than buy_account_id")
    return tx


async def get_fx_conversion(db: AsyncSession, conversion_id: uuid.UUID) -> FxConversion:
    result = await db.execute(select(FxConversion).where(FxConversion.id == conversion_id))
    conversion = result.scalar_one_or_none()
    if conversion is None:
        raise ValueError(f"FX conversion {conversion_id} not found")
    return conversion


async def list_fx_conversions(
    db: AsyncSession,
    currency: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[FxConversion], int]:
    query = select(FxConversion)

    if currency:
        query = query.where(
            (FxConversion.sell_currency == currency) | (FxConversion.buy_currency == currency)
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(FxConversion.conversion_date.desc(), FxConversion.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def _get_account(db: AsyncSession, account_id: uuid.UUID) -> Account:
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    return account
