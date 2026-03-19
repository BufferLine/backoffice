import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, get_current_user
from app.database import get_db
from app.schemas.changelog import ChangeLogListResponse, ChangeLogResponse
from app.services.changelog import get_changes_for_period, get_entity_history

router = APIRouter()


@router.get("/period/{start_date}/{end_date}", response_model=ChangeLogListResponse)
async def get_period_changes(
    start_date: date,
    end_date: date,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    entity_type: Optional[str] = None,
) -> ChangeLogListResponse:
    """Get all changes within a date range."""
    logs = await get_changes_for_period(db, start_date, end_date, entity_type=entity_type)
    return ChangeLogListResponse(
        items=[ChangeLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


@router.get("/{entity_type}/{entity_id}", response_model=ChangeLogListResponse)
async def get_entity_change_history(
    entity_type: str,
    entity_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeLogListResponse:
    """Get change history for an entity."""
    logs = await get_entity_history(db, entity_type, entity_id)
    return ChangeLogListResponse(
        items=[ChangeLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


@router.get("/{entity_type}/{entity_id}/{field_name}", response_model=ChangeLogListResponse)
async def get_field_change_history(
    entity_type: str,
    entity_id: uuid.UUID,
    field_name: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeLogListResponse:
    """Get change history for a specific field of an entity."""
    logs = await get_entity_history(db, entity_type, entity_id, field_name=field_name)
    return ChangeLogListResponse(
        items=[ChangeLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


@router.get("/period/{start_date}/{end_date}", response_model=ChangeLogListResponse)
async def get_period_changes(
    start_date: date,
    end_date: date,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    entity_type: Optional[str] = None,
) -> ChangeLogListResponse:
    """Get all changes within a date range."""
    logs = await get_changes_for_period(db, start_date, end_date, entity_type=entity_type)
    return ChangeLogListResponse(
        items=[ChangeLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )
