import calendar
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import TaskInstance, TaskTemplate
from app.schemas.task import (
    TaskInstanceCreate,
    TaskInstanceUpdate,
    TaskTemplateCreate,
    TaskTemplateUpdate,
    TodoSummary,
    TaskInstanceResponse,
)


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------


async def create_template(
    db: AsyncSession,
    data: TaskTemplateCreate,
    created_by: Optional[uuid.UUID] = None,
    is_system: bool = False,
) -> TaskTemplate:
    template = TaskTemplate(
        title=data.title,
        description=data.description,
        category=data.category,
        jurisdiction=data.jurisdiction,
        frequency=data.frequency,
        due_day=data.due_day,
        due_month=data.due_month,
        priority=data.priority or "medium",
        is_system=is_system,
        is_active=True,
        auto_generate=data.auto_generate if data.auto_generate is not None else True,
        created_by=created_by,
    )
    db.add(template)
    await db.flush()
    return template


async def update_template(
    db: AsyncSession,
    template_id: uuid.UUID,
    data: TaskTemplateUpdate,
) -> TaskTemplate:
    template = await get_template(db, template_id)
    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(template, key, value)
    await db.flush()
    return template


async def list_templates(
    db: AsyncSession,
    category: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> list[TaskTemplate]:
    query = select(TaskTemplate)
    if category is not None:
        query = query.where(TaskTemplate.category == category)
    if jurisdiction is not None:
        query = query.where(TaskTemplate.jurisdiction == jurisdiction)
    if is_active is not None:
        query = query.where(TaskTemplate.is_active == is_active)
    query = query.order_by(TaskTemplate.created_at.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: uuid.UUID) -> TaskTemplate:
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise ValueError(f"TaskTemplate {template_id} not found")
    return template


async def delete_template(db: AsyncSession, template_id: uuid.UUID) -> TaskTemplate:
    template = await get_template(db, template_id)
    if template.is_system:
        raise ValueError("Cannot delete system task templates")
    template.is_active = False
    await db.flush()
    return template


# ---------------------------------------------------------------------------
# Instance management
# ---------------------------------------------------------------------------


async def create_instance(
    db: AsyncSession,
    data: TaskInstanceCreate,
    created_by: Optional[uuid.UUID] = None,
) -> TaskInstance:
    instance = TaskInstance(
        template_id=data.template_id,
        title=data.title,
        description=data.description,
        category=data.category,
        priority=data.priority or "medium",
        period=data.period,
        due_date=data.due_date,
        status="pending",
        notes=data.notes,
        created_by=created_by,
    )
    db.add(instance)
    await db.flush()
    await db.refresh(instance)
    return instance


async def get_instance(db: AsyncSession, instance_id: uuid.UUID) -> TaskInstance:
    result = await db.execute(select(TaskInstance).where(TaskInstance.id == instance_id))
    instance = result.scalar_one_or_none()
    if instance is None:
        raise ValueError(f"TaskInstance {instance_id} not found")
    return instance


async def update_instance(
    db: AsyncSession,
    instance_id: uuid.UUID,
    data: TaskInstanceUpdate,
) -> TaskInstance:
    instance = await get_instance(db, instance_id)
    update_dict = data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(instance, key, value)
    await db.flush()
    await db.refresh(instance)
    return instance


async def complete_instance(
    db: AsyncSession,
    instance_id: uuid.UUID,
    user_id: uuid.UUID,
    notes: Optional[str] = None,
) -> TaskInstance:
    instance = await get_instance(db, instance_id)
    if instance.status not in ("pending", "in_progress", "overdue"):
        raise ValueError(f"Cannot complete task with status '{instance.status}'")
    instance.status = "completed"
    instance.completed_at = datetime.now(timezone.utc)
    instance.completed_by = user_id
    if notes is not None:
        instance.notes = notes
    await db.flush()
    await db.refresh(instance)
    return instance


async def skip_instance(
    db: AsyncSession,
    instance_id: uuid.UUID,
    user_id: uuid.UUID,
    notes: Optional[str] = None,
) -> TaskInstance:
    instance = await get_instance(db, instance_id)
    if instance.status not in ("pending", "in_progress", "overdue"):
        raise ValueError(f"Cannot skip task with status '{instance.status}'")
    instance.status = "skipped"
    if notes is not None:
        instance.notes = notes
    await db.flush()
    await db.refresh(instance)
    return instance


async def archive_instance(
    db: AsyncSession,
    instance_id: uuid.UUID,
    user_id: uuid.UUID,
) -> TaskInstance:
    instance = await get_instance(db, instance_id)
    if instance.status not in ("completed", "skipped"):
        raise ValueError(f"Cannot archive task with status '{instance.status}'. Complete or skip it first.")
    instance.status = "archived"
    await db.flush()
    await db.refresh(instance)
    return instance


async def list_instances(
    db: AsyncSession,
    period: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[TaskInstance], int]:
    query = select(TaskInstance)
    if period is not None:
        query = query.where(TaskInstance.period == period)
    if status is not None:
        query = query.where(TaskInstance.status == status)
    if category is not None:
        query = query.where(TaskInstance.category == category)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(TaskInstance.due_date.asc().nullslast(), TaskInstance.created_at.asc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def get_todo_summary(db: AsyncSession, period: str) -> TodoSummary:
    result = await db.execute(
        select(TaskInstance).where(TaskInstance.period == period)
    )
    items = list(result.scalars().all())

    pending = sum(1 for i in items if i.status == "pending")
    in_progress = sum(1 for i in items if i.status == "in_progress")
    completed = sum(1 for i in items if i.status == "completed")
    overdue = sum(1 for i in items if i.status == "overdue")

    return TodoSummary(
        period=period,
        pending=pending,
        in_progress=in_progress,
        completed=completed,
        overdue=overdue,
        items=[TaskInstanceResponse.model_validate(i) for i in items],
    )


# ---------------------------------------------------------------------------
# Auto-generation
# ---------------------------------------------------------------------------


def _quarter_for_month(month_num: int) -> int:
    """Return quarter number (1-4) for a given month."""
    return (month_num - 1) // 3 + 1


async def generate_instances_for_month(
    db: AsyncSession, month_str: str, *, backfill: bool = False,
) -> list[TaskInstance]:
    """Create task instances from active recurring templates for a given month.

    month_str format: 'YYYY-MM'
    backfill: if True, skip the unfinished-instance guard (used by generate_since)
    """
    year, month_num = map(int, month_str.split("-"))
    days_in_month = calendar.monthrange(year, month_num)[1]
    created: list[TaskInstance] = []

    # Fetch all active auto-generate templates
    templates_result = await db.execute(
        select(TaskTemplate).where(
            TaskTemplate.is_active == True,  # noqa: E712
            TaskTemplate.auto_generate == True,  # noqa: E712
            TaskTemplate.frequency != "once",
        )
    )
    templates = list(templates_result.scalars().all())

    for template in templates:
        period: Optional[str] = None
        due_date: Optional[date] = None

        if template.frequency == "monthly":
            period = month_str
            day = min(template.due_day or 1, days_in_month)
            due_date = date(year, month_num, day)

        elif template.frequency == "quarterly":
            # Only generate at quarter start months: 1, 4, 7, 10
            quarter_start_months = {1, 4, 7, 10}
            if month_num not in quarter_start_months:
                continue
            quarter_num = _quarter_for_month(month_num)
            period = f"{year}-Q{quarter_num}"
            # due_date: last day of the quarter's third month
            quarter_end_month = month_num + 2
            days_in_quarter_end = calendar.monthrange(year, quarter_end_month)[1]
            day = min(template.due_day or days_in_quarter_end, days_in_quarter_end)
            due_date = date(year, quarter_end_month, day)

        elif template.frequency == "yearly":
            # Only generate if current month matches template's due_month
            if template.due_month is not None and month_num != template.due_month:
                continue
            period = str(year)
            day = min(template.due_day or 1, days_in_month)
            due_date = date(year, month_num, day)

        else:
            continue

        if period is None:
            continue

        # Skip if instance already exists for (template_id, period)
        existing_result = await db.execute(
            select(TaskInstance).where(
                TaskInstance.template_id == template.id,
                TaskInstance.period == period,
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            continue

        # Skip if template already has an unfinished instance (pending/in_progress/overdue)
        # Unless backfill mode — backfill creates all missing periods regardless
        if not backfill:
            unfinished_result = await db.execute(
                select(TaskInstance).where(
                    TaskInstance.template_id == template.id,
                    TaskInstance.status.in_(["pending", "in_progress", "overdue"]),
                )
            )
            if unfinished_result.first() is not None:
                continue

        instance = TaskInstance(
            template_id=template.id,
            title=template.title,
            description=template.description,
            category=template.category,
            priority=template.priority,
            period=period,
            due_date=due_date,
            status="pending",
        )
        db.add(instance)
        await db.flush()
        await db.refresh(instance)
        created.append(instance)

    # Mark overdue: pending/in_progress instances from past periods with passed due_date
    today = date.today()
    overdue_result = await db.execute(
        select(TaskInstance).where(
            TaskInstance.status.in_(["pending", "in_progress"]),
            TaskInstance.due_date < today,
            TaskInstance.period != month_str,
        )
    )
    overdue_instances = list(overdue_result.scalars().all())
    for inst in overdue_instances:
        inst.status = "overdue"
    if overdue_instances:
        await db.flush()

    return created


async def generate_since(db: AsyncSession, since: str) -> list[TaskInstance]:
    """Backfill task instances from a past month to current month.

    since format: 'YYYY-MM'
    """
    since_year, since_month = map(int, since.split("-"))
    now = datetime.now(timezone.utc)
    current_year, current_month = now.year, now.month

    all_created: list[TaskInstance] = []
    y, m = since_year, since_month
    while (y, m) <= (current_year, current_month):
        month_str = f"{y:04d}-{m:02d}"
        created = await generate_instances_for_month(db, month_str, backfill=True)
        all_created.extend(created)
        m += 1
        if m > 12:
            m = 1
            y += 1

    return all_created


# ---------------------------------------------------------------------------
# Action todos (one-off from business events)
# ---------------------------------------------------------------------------


async def create_action_todo(
    db: AsyncSession,
    title: str,
    description: str,
    category: str,
    due_date: date,
    period: str,
    created_by,
    priority: str = "medium",
) -> TaskInstance:
    """Create a one-off action todo from a business event."""
    instance = TaskInstance(
        title=title,
        description=description,
        category=category,
        priority=priority,
        period=period,
        due_date=due_date,
        status="pending",
        created_by=created_by,
    )
    db.add(instance)
    await db.flush()
    return instance


# ---------------------------------------------------------------------------
# Smart features
# ---------------------------------------------------------------------------


async def get_upcoming(db: AsyncSession, days: int = 30) -> list[TaskInstance]:
    today = date.today()
    cutoff = date(today.year, today.month, today.day)
    from datetime import timedelta
    future = today + timedelta(days=days)
    result = await db.execute(
        select(TaskInstance).where(
            TaskInstance.status.in_(["pending", "in_progress"]),
            TaskInstance.due_date >= cutoff,
            TaskInstance.due_date <= future,
        ).order_by(TaskInstance.due_date.asc())
    )
    return list(result.scalars().all())


async def get_overdue(db: AsyncSession) -> list[TaskInstance]:
    result = await db.execute(
        select(TaskInstance)
        .where(TaskInstance.status == "overdue")
        .order_by(TaskInstance.due_date.asc())
    )
    return list(result.scalars().all())


async def add_note(
    db: AsyncSession,
    instance_id: uuid.UUID,
    note: str,
    user_id: uuid.UUID,
) -> TaskInstance:
    instance = await get_instance(db, instance_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_note = f"[{timestamp}] {note}"
    if instance.notes:
        instance.notes = instance.notes + "\n" + new_note
    else:
        instance.notes = new_note
    await db.flush()
    await db.refresh(instance)
    return instance


# ---------------------------------------------------------------------------
# Seed compliance data
# ---------------------------------------------------------------------------


async def seed_compliance_tasks(db: AsyncSession) -> None:
    """Seed system task templates for Singapore compliance. Idempotent."""
    system_templates = [
        # Singapore — Payroll
        {
            "title": "SDL Payment",
            "description": "Skills Development Levy monthly payment",
            "category": "payroll",
            "jurisdiction": "SG",
            "frequency": "monthly",
            "due_day": 14,
            "due_month": None,
            "priority": "high",
        },
        {
            "title": "CPF Payment",
            "description": "Central Provident Fund monthly contribution",
            "category": "payroll",
            "jurisdiction": "SG",
            "frequency": "monthly",
            "due_day": 14,
            "due_month": None,
            "priority": "high",
        },
        {
            "title": "Run Payroll",
            "description": "Process monthly payroll for all employees",
            "category": "payroll",
            "jurisdiction": "SG",
            "frequency": "monthly",
            "due_day": 25,
            "due_month": None,
            "priority": "high",
        },
        # Singapore — Tax
        {
            "title": "GST Filing (F5)",
            "description": "Quarterly GST F5 return submission",
            "category": "tax",
            "jurisdiction": "SG",
            "frequency": "quarterly",
            "due_day": 28,
            "due_month": None,
            "priority": "high",
        },
        {
            "title": "Annual Income Tax (Form C-S)",
            "description": "Annual corporate income tax filing Form C-S",
            "category": "tax",
            "jurisdiction": "SG",
            "frequency": "yearly",
            "due_day": 30,
            "due_month": 11,
            "priority": "high",
        },
        # Singapore — Filing
        {
            "title": "IR8A Submission",
            "description": "Annual IR8A employee income submission to IRAS",
            "category": "filing",
            "jurisdiction": "SG",
            "frequency": "yearly",
            "due_day": 1,
            "due_month": 3,
            "priority": "high",
        },
        {
            "title": "AGM Filing",
            "description": "Annual General Meeting filing with ACRA",
            "category": "filing",
            "jurisdiction": "SG",
            "frequency": "yearly",
            "due_day": 31,
            "due_month": 12,
            "priority": "medium",
        },
        # Operations
        {
            "title": "Review Monthly Expenses",
            "description": "Review and approve all monthly expense submissions",
            "category": "operations",
            "jurisdiction": None,
            "frequency": "monthly",
            "due_day": 28,
            "due_month": None,
            "priority": "medium",
        },
        {
            "title": "Month-End Export Pack",
            "description": "Generate and archive the month-end export pack",
            "category": "operations",
            "jurisdiction": None,
            "frequency": "monthly",
            "due_day": 28,
            "due_month": None,
            "priority": "medium",
        },
        {
            "title": "Review Outstanding Invoices",
            "description": "Review and follow up on outstanding client invoices",
            "category": "operations",
            "jurisdiction": None,
            "frequency": "monthly",
            "due_day": 1,
            "due_month": None,
            "priority": "medium",
        },
    ]

    for tmpl_data in system_templates:
        # Check if already exists by title + is_system
        existing_result = await db.execute(
            select(TaskTemplate).where(
                TaskTemplate.title == tmpl_data["title"],
                TaskTemplate.is_system == True,  # noqa: E712
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            continue

        data = TaskTemplateCreate(
            title=tmpl_data["title"],
            description=tmpl_data.get("description"),
            category=tmpl_data.get("category"),
            jurisdiction=tmpl_data.get("jurisdiction"),
            frequency=tmpl_data["frequency"],
            due_day=tmpl_data.get("due_day"),
            due_month=tmpl_data.get("due_month"),
            priority=tmpl_data.get("priority", "medium"),
            auto_generate=True,
        )
        await create_template(db, data, created_by=None, is_system=True)
