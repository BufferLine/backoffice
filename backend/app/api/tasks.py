import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.task import (
    TaskInstanceCreate,
    TaskInstanceResponse,
    TaskInstanceUpdate,
    TaskListResponse,
    TaskTemplateCreate,
    TaskTemplateResponse,
    TaskTemplateUpdate,
    TodoSummary,
)
from app.services import task as task_svc

router = APIRouter()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.post("/templates", response_model=TaskTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TaskTemplateCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskTemplateResponse:
    template = await task_svc.create_template(db, data, created_by=current_user.id)
    return TaskTemplateResponse.model_validate(template)


@router.get("/templates", response_model=list[TaskTemplateResponse])
async def list_templates(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> list[TaskTemplateResponse]:
    templates = await task_svc.list_templates(db, category=category, jurisdiction=jurisdiction, is_active=is_active)
    return [TaskTemplateResponse.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=TaskTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskTemplateResponse:
    try:
        template = await task_svc.get_template(db, template_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskTemplateResponse.model_validate(template)


@router.patch("/templates/{template_id}", response_model=TaskTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    data: TaskTemplateUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskTemplateResponse:
    try:
        template = await task_svc.update_template(db, template_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await task_svc.delete_template(db, template_id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


# ---------------------------------------------------------------------------
# Summary / smart endpoints — must come BEFORE /{id} to avoid path conflicts
# ---------------------------------------------------------------------------


@router.get("/todo", response_model=TodoSummary)
async def get_todo_current(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TodoSummary:
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    return await task_svc.get_todo_summary(db, period)


@router.get("/todo/{period}", response_model=TodoSummary)
async def get_todo_period(
    period: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TodoSummary:
    return await task_svc.get_todo_summary(db, period)


@router.get("/upcoming", response_model=list[TaskInstanceResponse])
async def get_upcoming(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 30,
) -> list[TaskInstanceResponse]:
    items = await task_svc.get_upcoming(db, days=days)
    return [TaskInstanceResponse.model_validate(i) for i in items]


@router.get("/overdue", response_model=list[TaskInstanceResponse])
async def get_overdue(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TaskInstanceResponse]:
    items = await task_svc.get_overdue(db)
    return [TaskInstanceResponse.model_validate(i) for i in items]


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------


@router.post("", response_model=TaskInstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    data: TaskInstanceCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskInstanceResponse:
    instance = await task_svc.create_instance(db, data, created_by=current_user.id)
    return TaskInstanceResponse.model_validate(instance)


@router.get("", response_model=TaskListResponse)
async def list_instances(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> TaskListResponse:
    items, total = await task_svc.list_instances(
        db, period=period, status=status, category=category, page=page, per_page=per_page
    )
    return TaskListResponse(
        items=[TaskInstanceResponse.model_validate(i) for i in items],
        total=total,
    )


@router.get("/{instance_id}", response_model=TaskInstanceResponse)
async def get_instance(
    instance_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskInstanceResponse:
    try:
        instance = await task_svc.get_instance(db, instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskInstanceResponse.model_validate(instance)


@router.patch("/{instance_id}", response_model=TaskInstanceResponse)
async def update_instance(
    instance_id: uuid.UUID,
    data: TaskInstanceUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskInstanceResponse:
    try:
        instance = await task_svc.update_instance(db, instance_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskInstanceResponse.model_validate(instance)


@router.post("/{instance_id}/complete", response_model=TaskInstanceResponse)
async def complete_instance(
    instance_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: Optional[str] = None,
) -> TaskInstanceResponse:
    try:
        instance = await task_svc.complete_instance(db, instance_id, current_user.id, notes=notes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskInstanceResponse.model_validate(instance)


@router.post("/{instance_id}/skip", response_model=TaskInstanceResponse)
async def skip_instance(
    instance_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    notes: Optional[str] = None,
) -> TaskInstanceResponse:
    try:
        instance = await task_svc.skip_instance(db, instance_id, current_user.id, notes=notes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskInstanceResponse.model_validate(instance)


@router.post("/{instance_id}/note", response_model=TaskInstanceResponse)
async def add_note(
    instance_id: uuid.UUID,
    note: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("expense:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskInstanceResponse:
    try:
        instance = await task_svc.add_note(db, instance_id, note, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TaskInstanceResponse.model_validate(instance)
