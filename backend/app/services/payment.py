import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payroll import PayrollRun
from app.schemas.payment import PaymentCreate
from app.services.audit import AuditService
from app.state_machines.invoice import invoice_machine
from app.state_machines.payroll import payroll_machine


async def record_payment(
    db: AsyncSession,
    data: PaymentCreate,
    created_by: uuid.UUID,
) -> Payment:
    # Idempotency: return existing if idempotency_key found
    if data.idempotency_key:
        result = await db.execute(
            select(Payment).where(Payment.idempotency_key == data.idempotency_key)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

    # tx_hash uniqueness check
    if data.tx_hash:
        result = await db.execute(
            select(Payment).where(Payment.tx_hash == data.tx_hash)
        )
        duplicate = result.scalar_one_or_none()
        if duplicate is not None:
            raise ValueError(f"Duplicate tx_hash: {data.tx_hash}")

    # Compute SGD value if fx_rate provided
    sgd_value = None
    if data.fx_rate_to_sgd is not None:
        sgd_value = Decimal(str(data.amount)) * Decimal(str(data.fx_rate_to_sgd))

    payment = Payment(
        payment_type=data.payment_type,
        related_entity_type=data.related_entity_type,
        related_entity_id=data.related_entity_id,
        payment_date=data.payment_date,
        currency=data.currency,
        amount=data.amount,
        fx_rate_to_sgd=data.fx_rate_to_sgd,
        fx_rate_date=data.fx_rate_date,
        fx_rate_source=data.fx_rate_source,
        sgd_value=sgd_value,
        tx_hash=data.tx_hash,
        chain_id=data.chain_id,
        bank_reference=data.bank_reference,
        idempotency_key=data.idempotency_key,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError("Duplicate payment (tx_hash or idempotency_key conflict)") from e

    await AuditService(db).log(
        action="payment.create",
        entity_type="payment",
        entity_id=payment.id,
        actor_id=created_by,
        input_data=data.model_dump(mode="json"),
    )
    return payment


async def get_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise ValueError(f"Payment {payment_id} not found")
    return payment


async def list_payments(
    db: AsyncSession,
    entity_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Payment], int]:
    query = select(Payment)

    if entity_type:
        query = query.where(Payment.related_entity_type == entity_type)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Payment.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def link_payment(
    db: AsyncSession,
    payment_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> Payment:
    payment = await get_payment(db, payment_id)

    # Prevent reassigning a payment already linked elsewhere
    if payment.related_entity_id is not None and payment.related_entity_id != entity_id:
        raise ValueError(
            f"Payment {payment_id} is already linked to {payment.related_entity_type} "
            f"{payment.related_entity_id}"
        )

    if entity_type == "invoice":
        result = await db.execute(select(Invoice).where(Invoice.id == entity_id))
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise ValueError(f"Invoice {entity_id} not found")
        if invoice.status != "issued":
            raise ValueError(f"Invoice must be in 'issued' state to link payment, current: {invoice.status}")

        # Validate amount and currency
        if float(payment.amount) < float(invoice.total_amount):
            raise ValueError(
                f"Payment amount {payment.amount} is less than invoice total {invoice.total_amount}"
            )
        if payment.currency != invoice.currency:
            raise ValueError(
                f"Payment currency {payment.currency} does not match invoice currency {invoice.currency}"
            )

        new_state = invoice_machine.transition(invoice.status, "mark_paid")
        invoice.status = new_state
        await db.flush()
        await AuditService(db).log(
            action="invoice.mark_paid",
            entity_type="invoice",
            entity_id=invoice.id,
            actor_id=actor_id,
            input_data={"payment_id": str(payment_id)},
            output_data={"status": new_state},
        )

    elif entity_type == "payroll_run":
        result = await db.execute(select(PayrollRun).where(PayrollRun.id == entity_id))
        payroll_run = result.scalar_one_or_none()
        if payroll_run is None:
            raise ValueError(f"PayrollRun {entity_id} not found")
        if payroll_run.status != "finalized":
            raise ValueError(f"PayrollRun must be in 'finalized' state to link payment, current: {payroll_run.status}")

        # Validate amount and currency
        if float(payment.amount) != float(payroll_run.net_salary):
            raise ValueError(
                f"Payment amount {payment.amount} does not match payroll net salary {payroll_run.net_salary}"
            )
        if payment.currency != payroll_run.currency:
            raise ValueError(
                f"Payment currency {payment.currency} does not match payroll currency {payroll_run.currency}"
            )

        # Transition payroll run to paid
        from datetime import datetime, timezone
        new_state = payroll_machine.transition(payroll_run.status, "mark_paid")
        payroll_run.status = new_state
        payroll_run.paid_at = datetime.now(tz=timezone.utc)
        payroll_run.payment_id = payment.id
        await db.flush()
        await AuditService(db).log(
            action="payroll.mark_paid",
            entity_type="payroll_run",
            entity_id=payroll_run.id,
            actor_id=actor_id,
            input_data={"payment_id": str(payment_id)},
            output_data={"status": new_state},
        )

    payment.related_entity_type = entity_type
    payment.related_entity_id = entity_id
    await db.flush()

    await AuditService(db).log(
        action="payment.link",
        entity_type="payment",
        entity_id=payment.id,
        actor_id=actor_id,
        input_data={"entity_type": entity_type, "entity_id": str(entity_id)},
    )
    return payment
