import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.loan import Loan
from app.models.payment import Payment
from app.models.payment_allocation import PaymentAllocation
from app.models.payroll import PayrollRun
from app.services.audit import AuditService


_ENTITY_MODEL_MAP = {
    "invoice": Invoice,
    "expense": Expense,
    "loan": Loan,
    "payroll": PayrollRun,
}


async def _sum_existing_allocations(db: AsyncSession, payment_id: uuid.UUID) -> Decimal:
    result = await db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.payment_id == payment_id
        )
    )
    return Decimal(str(result.scalar_one()))


async def allocate_payment(
    db: AsyncSession,
    payment_id: uuid.UUID,
    allocations: list,
    user_id: uuid.UUID,
) -> tuple[list[PaymentAllocation], Decimal]:
    """Allocate a payment to one or more documents.

    Returns (created_allocations, unallocated_amount).
    Raises ValueError on validation failure.
    """
    # Verify payment exists
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise ValueError(f"Payment {payment_id} not found")

    payment_amount = Decimal(str(payment.amount))
    existing_allocated = await _sum_existing_allocations(db, payment_id)
    available = payment_amount - existing_allocated

    # Validate total of new allocations fits within available
    new_total = sum(Decimal(str(a.amount)) for a in allocations)
    if new_total > available:
        raise ValueError(
            f"Allocation total {new_total} exceeds available amount {available} "
            f"(payment {payment_amount} - already allocated {existing_allocated})"
        )

    created = []
    for alloc in allocations:
        entity_type = alloc.entity_type
        entity_id = alloc.entity_id
        amount = Decimal(str(alloc.amount))

        if amount <= 0:
            raise ValueError(f"Allocation amount must be positive, got {amount}")

        model = _ENTITY_MODEL_MAP.get(entity_type)
        if model is None:
            raise ValueError(
                f"Unknown entity_type '{entity_type}'. "
                f"Must be one of: {', '.join(_ENTITY_MODEL_MAP)}"
            )

        entity_result = await db.execute(select(model).where(model.id == entity_id))
        entity = entity_result.scalar_one_or_none()
        if entity is None:
            raise ValueError(f"{entity_type} {entity_id} not found")

        record = PaymentAllocation(
            payment_id=payment_id,
            entity_type=entity_type,
            entity_id=entity_id,
            amount=float(amount),
            notes=alloc.notes,
            created_by=user_id,
        )
        db.add(record)
        created.append(record)

    await db.flush()

    await AuditService(db).log(
        action="payment_allocation.create",
        entity_type="payment",
        entity_id=payment_id,
        actor_id=user_id,
        input_data={
            "allocations": [
                {
                    "entity_type": a.entity_type,
                    "entity_id": str(a.entity_id),
                    "amount": str(a.amount),
                }
                for a in allocations
            ]
        },
        output_data={"count": len(created)},
    )

    new_existing = existing_allocated + new_total
    unallocated = payment_amount - new_existing
    return created, unallocated


async def get_payment_allocations(
    db: AsyncSession,
    payment_id: uuid.UUID,
) -> list[PaymentAllocation]:
    """Return all allocations for a payment."""
    result = await db.execute(
        select(PaymentAllocation)
        .where(PaymentAllocation.payment_id == payment_id)
        .order_by(PaymentAllocation.created_at)
    )
    return list(result.scalars().all())


async def get_entity_allocations(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
) -> list[PaymentAllocation]:
    """Return all allocations targeting a specific entity."""
    result = await db.execute(
        select(PaymentAllocation)
        .where(
            PaymentAllocation.entity_type == entity_type,
            PaymentAllocation.entity_id == entity_id,
        )
        .order_by(PaymentAllocation.created_at)
    )
    return list(result.scalars().all())


async def get_outstanding(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    total_amount: Decimal,
) -> Decimal:
    """Return outstanding balance: total_amount minus sum of allocations for this entity."""
    result = await db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.entity_type == entity_type,
            PaymentAllocation.entity_id == entity_id,
        )
    )
    allocated = Decimal(str(result.scalar_one()))
    return total_amount - allocated


async def deallocate(
    db: AsyncSession,
    allocation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete a single allocation record and write an audit log entry."""
    result = await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.id == allocation_id)
    )
    allocation = result.scalar_one_or_none()
    if allocation is None:
        raise ValueError(f"Allocation {allocation_id} not found")

    payment_id = allocation.payment_id
    entity_type = allocation.entity_type
    entity_id = allocation.entity_id

    await db.delete(allocation)
    await db.flush()

    await AuditService(db).log(
        action="payment_allocation.delete",
        entity_type="payment",
        entity_id=payment_id,
        actor_id=user_id,
        input_data={
            "allocation_id": str(allocation_id),
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        },
    )
