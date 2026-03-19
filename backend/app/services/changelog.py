import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.changelog import ChangeLog


def _serialize_value(value: Any) -> Optional[str]:
    """Convert any value to string for storage."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


async def track_changes(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    changed_by: Optional[uuid.UUID] = None,
    effective_date: Optional[date] = None,
    reason: Optional[str] = None,
    exclude_fields: Optional[set[str]] = None,
) -> list[ChangeLog]:
    """Compare old and new values, create ChangeLog entries for differences.

    Usage:
        # Before update, snapshot current values
        old = {"base_salary": employee.base_salary, "status": employee.status}
        # Apply update
        employee.base_salary = new_salary
        # Track
        await track_changes(db, "employee", employee.id, old, {"base_salary": new_salary}, user_id)
    """
    exclude = exclude_fields or {"updated_at", "created_at", "id", "password_hash"}
    logs = []

    for field, new_val in new_values.items():
        if field in exclude:
            continue
        old_val = old_values.get(field)
        old_str = _serialize_value(old_val)
        new_str = _serialize_value(new_val)

        if old_str != new_str:
            log = ChangeLog(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field,
                old_value=old_str,
                new_value=new_str,
                effective_date=effective_date,
                reason=reason,
                changed_by=changed_by,
            )
            db.add(log)
            logs.append(log)

    if logs:
        await db.flush()
    return logs


async def track_entity_update(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    update_data: dict[str, Any],
    changed_by: Optional[uuid.UUID] = None,
    effective_date: Optional[date] = None,
    reason: Optional[str] = None,
) -> list[ChangeLog]:
    """Convenience: snapshot entity, apply updates, track changes.

    Usage:
        logs = await track_entity_update(db, "employee", employee, {"base_salary": 10000}, user_id)
    """
    old_values = {}
    for field in update_data:
        if hasattr(entity, field):
            old_values[field] = getattr(entity, field)

    # Apply updates
    for field, value in update_data.items():
        if hasattr(entity, field):
            setattr(entity, field, value)

    return await track_changes(
        db, entity_type, entity.id, old_values, update_data,
        changed_by=changed_by, effective_date=effective_date, reason=reason,
    )


async def track_status_change(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    old_status: str,
    new_status: str,
    changed_by: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
) -> ChangeLog:
    """Track a status transition specifically."""
    log = ChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        field_name="status",
        old_value=old_status,
        new_value=new_status,
        reason=reason,
        changed_by=changed_by,
    )
    db.add(log)
    await db.flush()
    return log


async def get_entity_history(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    field_name: Optional[str] = None,
) -> list[ChangeLog]:
    """Get change history for an entity, optionally filtered by field."""
    query = (
        select(ChangeLog)
        .where(ChangeLog.entity_type == entity_type, ChangeLog.entity_id == entity_id)
        .order_by(ChangeLog.created_at.desc())
    )
    if field_name:
        query = query.where(ChangeLog.field_name == field_name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_changes_for_period(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    entity_type: Optional[str] = None,
) -> list[ChangeLog]:
    """Get all changes within a date range, for export packs."""
    from sqlalchemy import cast, Date as SqlDate
    query = (
        select(ChangeLog)
        .where(
            cast(ChangeLog.created_at, SqlDate) >= start_date,
            cast(ChangeLog.created_at, SqlDate) <= end_date,
        )
        .order_by(ChangeLog.created_at.desc())
    )
    if entity_type:
        query = query.where(ChangeLog.entity_type == entity_type)
    result = await db.execute(query)
    return list(result.scalars().all())
