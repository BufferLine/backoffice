import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fx_conversion import FxConversion
from app.schemas.fx_conversion import FxConversionCreate
from app.schemas.journal import JournalEntryCreate, JournalLineCreate
from app.services.audit import AuditService
from app.services.journal import create_journal_entry


async def record_fx_conversion(
    db: AsyncSession,
    data: FxConversionCreate,
    created_by: uuid.UUID,
) -> FxConversion:
    """Record an FX conversion and auto-create a balanced journal entry.

    The journal entry is recorded in SGD (functional currency):
    - Debit: buy_account (foreign currency account) — SGD equivalent
    - Credit: sell_account (source currency account) — SGD equivalent

    If one side is SGD, that amount is the SGD value.
    If neither side is SGD, sell_amount is treated as the SGD equivalent
    (caller must provide SGD-equivalent amounts or a separate fx_rate_to_sgd).
    """
    # Validate accounts exist and match currencies
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

    # Compute FX rate: how much sell_currency per 1 buy_currency
    fx_rate = Decimal(str(data.sell_amount)) / Decimal(str(data.buy_amount))

    # Determine fx_rate_to_sgd for each line
    if data.sell_currency == "SGD":
        sell_fx_rate = Decimal("1")
        buy_fx_rate = fx_rate  # SGD per 1 buy_currency
    else:
        buy_fx_rate = Decimal("1")
        sell_fx_rate = Decimal("1") / fx_rate  # SGD per 1 sell_currency

    # Create journal entry with native currency amounts on each line.
    # Balance is validated in SGD equivalent via fx_rate_to_sgd.
    journal_data = JournalEntryCreate(
        entry_date=data.conversion_date,
        description=(
            f"FX conversion: {data.sell_currency} {data.sell_amount:,.2f} → "
            f"{data.buy_currency} {data.buy_amount:,.2f} @ {fx_rate:.6f}"
        ),
        source_type="fx_conversion",
        is_confirmed=True,
        lines=[
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
        ],
    )
    journal_entry = await create_journal_entry(db, journal_data, created_by=created_by)

    conversion = FxConversion(
        conversion_date=data.conversion_date,
        sell_currency=data.sell_currency,
        sell_amount=data.sell_amount,
        buy_currency=data.buy_currency,
        buy_amount=data.buy_amount,
        fx_rate=fx_rate,
        sell_account_id=data.sell_account_id,
        buy_account_id=data.buy_account_id,
        journal_entry_id=journal_entry.id,
        provider=data.provider,
        reference=data.reference,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(conversion)
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
        },
    )
    return conversion


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
