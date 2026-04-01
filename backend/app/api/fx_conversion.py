import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.fx_conversion import (
    FxConversionCreate,
    FxConversionListResponse,
    FxConversionResponse,
)
from app.services import fx_conversion as fx_svc

router = APIRouter()


@router.post("", response_model=FxConversionResponse, status_code=status.HTTP_201_CREATED)
async def record_fx_conversion(
    data: FxConversionCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("journal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FxConversionResponse:
    """Record an FX conversion with auto-generated journal entry."""
    try:
        conversion = await fx_svc.record_fx_conversion(db, data, current_user.id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return FxConversionResponse.model_validate(conversion)


@router.get("", response_model=FxConversionListResponse)
async def list_fx_conversions(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("journal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    currency: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> FxConversionListResponse:
    items, total = await fx_svc.list_fx_conversions(db, currency=currency, page=page, per_page=per_page)
    return FxConversionListResponse(
        items=[FxConversionResponse.model_validate(c) for c in items],
        total=total,
    )


@router.get("/{conversion_id}", response_model=FxConversionResponse)
async def get_fx_conversion(
    conversion_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("journal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FxConversionResponse:
    try:
        conversion = await fx_svc.get_fx_conversion(db, conversion_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return FxConversionResponse.model_validate(conversion)
