import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services.audit import AuditService


async def create_transaction(
    db: AsyncSession,
    data: TransactionCreate,
    created_by: Optional[uuid.UUID] = None,
) -> Transaction:
    sgd_value = data.sgd_value
    if sgd_value is None and data.fx_rate_to_sgd is not None:
        sgd_value = data.amount * data.fx_rate_to_sgd

    confirmed_at = None
    if data.status == "confirmed":
        confirmed_at = datetime.now(tz=timezone.utc)

    tx = Transaction(
        account_id=data.account_id,
        direction=data.direction,
        amount=data.amount,
        currency=data.currency,
        tx_date=data.tx_date,
        status=data.status,
        category=data.category,
        counterparty=data.counterparty,
        description=data.description,
        reference=data.reference,
        payment_id=data.payment_id,
        bank_transaction_id=data.bank_transaction_id,
        recurring_commitment_id=data.recurring_commitment_id,
        fx_rate_to_sgd=data.fx_rate_to_sgd,
        sgd_value=sgd_value,
        notes=data.notes,
        metadata_json=data.metadata_json,
        confirmed_at=confirmed_at,
        created_by=created_by,
    )
    db.add(tx)
    await db.flush()

    await AuditService(db).log(
        action="transaction.create",
        entity_type="transaction",
        entity_id=tx.id,
        actor_id=created_by,
        input_data=data.model_dump(mode="json"),
    )
    return tx


async def get_transaction(db: AsyncSession, tx_id: uuid.UUID) -> Transaction:
    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if tx is None:
        raise ValueError(f"Transaction {tx_id} not found")
    return tx


async def confirm_transaction(
    db: AsyncSession,
    tx_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
) -> Transaction:
    tx = await get_transaction(db, tx_id)
    if tx.status == "confirmed":
        return tx
    if tx.status == "cancelled":
        raise ValueError("Cannot confirm a cancelled transaction")

    tx.status = "confirmed"
    tx.confirmed_at = datetime.now(tz=timezone.utc)
    await db.flush()

    await AuditService(db).log(
        action="transaction.confirm",
        entity_type="transaction",
        entity_id=tx.id,
        actor_id=user_id,
        output_data={"status": "confirmed"},
    )
    return tx


async def cancel_transaction(
    db: AsyncSession,
    tx_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
) -> Transaction:
    tx = await get_transaction(db, tx_id)
    if tx.status == "cancelled":
        return tx
    if tx.status == "confirmed":
        raise ValueError("Cannot cancel a confirmed transaction")

    tx.status = "cancelled"
    await db.flush()

    await AuditService(db).log(
        action="transaction.cancel",
        entity_type="transaction",
        entity_id=tx.id,
        actor_id=user_id,
        output_data={"status": "cancelled"},
    )
    return tx


async def update_transaction(
    db: AsyncSession,
    tx_id: uuid.UUID,
    data: TransactionUpdate,
    user_id: Optional[uuid.UUID] = None,
) -> Transaction:
    tx = await get_transaction(db, tx_id)
    if tx.status != "pending":
        raise ValueError("Only pending transactions can be updated")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tx, field, value)
    await db.flush()
    return tx


async def list_transactions(
    db: AsyncSession,
    account_id: Optional[uuid.UUID] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[object] = None,
    end_date: Optional[object] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Transaction], int]:
    query = select(Transaction)

    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if category:
        query = query.where(Transaction.category == category)
    if status:
        query = query.where(Transaction.status == status)
    if start_date:
        query = query.where(Transaction.tx_date >= start_date)
    if end_date:
        query = query.where(Transaction.tx_date <= end_date)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Transaction.tx_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def create_transaction_from_payment(
    db: AsyncSession,
    payment: Payment,
    account_id: uuid.UUID,
    direction: str,
    category: str,
    created_by: Optional[uuid.UUID] = None,
) -> Transaction:
    from app.schemas.transaction import TransactionCreate
    from datetime import date

    tx_date = payment.payment_date if payment.payment_date else date.today()

    data = TransactionCreate(
        account_id=account_id,
        direction=direction,
        amount=payment.amount,
        currency=payment.currency,
        tx_date=tx_date,
        status="confirmed",
        category=category,
        payment_id=payment.id,
        fx_rate_to_sgd=payment.fx_rate_to_sgd,
        sgd_value=payment.sgd_value,
        notes=payment.notes,
    )
    return await create_transaction(db, data, created_by=created_by)
