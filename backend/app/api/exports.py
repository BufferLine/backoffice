import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.export import (
    ExportListResponse,
    ExportPackResponse,
    ExportValidationResult,
    MonthEndRequest,
)
from app.services import export as export_svc
from app.services.file_storage import FileStorageService, get_file_storage

router = APIRouter()


@router.post("/validate/{month}", response_model=ExportValidationResult)
async def validate_month(
    month: str,
    current_user: Annotated[AuthenticatedUser, require_permission("export:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportValidationResult:
    try:
        return await export_svc.validate_month(db, month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/month-end", response_model=ExportPackResponse, status_code=status.HTTP_201_CREATED)
async def generate_month_end(
    body: MonthEndRequest,
    current_user: Annotated[AuthenticatedUser, require_permission("export:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> ExportPackResponse:
    try:
        pack = await export_svc.generate_month_end_pack(
            db=db,
            month_str=body.month,
            force=body.force,
            user_id=current_user.id,
            file_storage=file_storage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return ExportPackResponse.model_validate(pack)


@router.get("", response_model=ExportListResponse)
async def list_exports(
    current_user: Annotated[AuthenticatedUser, require_permission("export:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    per_page: int = 20,
) -> ExportListResponse:
    items, total = await export_svc.list_exports(db, page=page, per_page=per_page)
    return ExportListResponse(
        items=[ExportPackResponse.model_validate(p) for p in items],
        total=total,
    )


@router.get("/{export_id}", response_model=ExportPackResponse)
async def get_export(
    export_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("export:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportPackResponse:
    pack = await export_svc.get_export(db, export_id)
    if pack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export pack not found")
    return ExportPackResponse.model_validate(pack)


@router.get("/{export_id}/download")
async def get_export_download(
    export_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("export:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> dict:
    try:
        url = await export_svc.get_export_download_url(db, export_id, file_storage)
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return {"download_url": url}
