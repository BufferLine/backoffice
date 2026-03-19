from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.export import AutomationResult
from app.services import automation as automation_svc
from app.services.file_storage import FileStorageService, get_file_storage

router = APIRouter()


@router.post("/daily", response_model=AutomationResult)
async def run_daily(
    current_user: Annotated[AuthenticatedUser, require_permission("export:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutomationResult:
    try:
        return await automation_svc.run_daily(db)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/weekly", response_model=AutomationResult)
async def run_weekly(
    current_user: Annotated[AuthenticatedUser, require_permission("export:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutomationResult:
    try:
        return await automation_svc.run_weekly(db)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/monthly", response_model=AutomationResult)
async def run_monthly(
    current_user: Annotated[AuthenticatedUser, require_permission("export:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
    month: str = Query(..., description="Month in YYYY-MM format"),
) -> AutomationResult:
    try:
        return await automation_svc.run_monthly(
            db=db,
            month_str=month,
            file_storage=file_storage,
            system_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
