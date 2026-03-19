import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.payment import Payment
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services.audit import AuditService
from app.services.changelog import track_status_change
from app.state_machines.expense import expense_machine
from app.state_machines import InvalidTransitionError


async def create_expense(
    db: AsyncSession,
    data: ExpenseCreate,
    created_by: uuid.UUID,
) -> Expense:
    expense = Expense(
        expense_date=data.expense_date,
        vendor=data.vendor,
        category=data.category,
        currency=data.currency,
        amount=data.amount,
        payment_method=data.payment_method,
        reimbursable=data.reimbursable or False,
        notes=data.notes,
        status="draft",
        created_by=created_by,
    )
    db.add(expense)
    await db.flush()
    await AuditService(db).log(
        action="expense.create",
        entity_type="expense",
        entity_id=expense.id,
        actor_id=created_by,
        input_data=data.model_dump(mode="json"),
    )
    return expense


async def update_expense(
    db: AsyncSession,
    expense_id: uuid.UUID,
    data: ExpenseUpdate,
) -> Expense:
    expense = await get_expense(db, expense_id)
    if expense.status != "draft":
        raise InvalidTransitionError("expense", expense.status, "update")
    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(expense, key, value)
    await db.flush()
    return expense


async def confirm_expense(
    db: AsyncSession,
    expense_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Expense:
    expense = await get_expense(db, expense_id)
    old_state = expense.status
    new_state = expense_machine.transition(expense.status, "confirm")
    expense.status = new_state
    await db.flush()
    await track_status_change(db, "expense", expense.id, old_state, new_state, changed_by=user_id)
    await AuditService(db).log(
        action="expense.confirm",
        entity_type="expense",
        entity_id=expense.id,
        actor_id=user_id,
        input_data={"previous_status": "draft"},
        output_data={"status": new_state},
    )
    return expense


async def reimburse_expense(
    db: AsyncSession,
    expense_id: uuid.UUID,
    payment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Expense:
    expense = await get_expense(db, expense_id)
    if not expense.reimbursable:
        raise ValueError("Expense is not marked as reimbursable")

    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise ValueError(f"Payment {payment_id} not found")

    old_state = expense.status
    new_state = expense_machine.transition(expense.status, "reimburse")
    expense.status = new_state
    await db.flush()
    await track_status_change(db, "expense", expense.id, old_state, new_state, changed_by=user_id)
    await AuditService(db).log(
        action="expense.reimburse",
        entity_type="expense",
        entity_id=expense.id,
        actor_id=user_id,
        input_data={"payment_id": str(payment_id)},
        output_data={"status": new_state},
    )
    return expense


async def get_expense(db: AsyncSession, expense_id: uuid.UUID) -> Expense:
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    expense = result.scalar_one_or_none()
    if expense is None:
        raise ValueError(f"Expense {expense_id} not found")
    return expense


async def list_expenses(
    db: AsyncSession,
    month: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Expense], int]:
    query = select(Expense)

    if month:
        # month expected as "YYYY-MM"
        try:
            year, mon = month.split("-")
            query = query.where(
                func.to_char(Expense.expense_date, "YYYY-MM") == month
            )
        except ValueError:
            pass

    if category:
        query = query.where(Expense.category == category)

    if status:
        query = query.where(Expense.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(Expense.expense_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total
