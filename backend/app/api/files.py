import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.file import File
from app.services.file_storage import FileStorageService, get_file_storage, safe_filename

router = APIRouter()


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("file:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> StreamingResponse:
    """Download a file by ID. Returns the file content directly."""
    result = await db.execute(select(File).where(File.id == file_id))
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    content = file_storage.download(file_record.storage_key)
    return StreamingResponse(
        io.BytesIO(content),
        media_type=file_record.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename(file_record.original_filename)}"',
            "Content-Length": str(len(content)),
        },
    )


@router.get("/{file_id}/url")
async def get_file_url(
    file_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("file:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> dict:
    """Get a presigned download URL for a file."""
    result = await db.execute(select(File).where(File.id == file_id))
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    url = file_storage.get_presigned_url(file_record.storage_key)
    return {"url": url, "filename": file_record.original_filename, "mime_type": file_record.mime_type}
