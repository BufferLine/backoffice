from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, get_current_user, require_permission
from app.database import get_db
from app.models.company import CompanySettings
from app.models.currency import Currency
from app.models.file import File as FileRecord
from app.schemas.company import (
    CompanySettingsResponse,
    CompanySettingsUpdate,
    CurrencyCreate,
    CurrencyResponse,
)
from app.services.file_storage import FileStorageService, get_file_storage

router = APIRouter()

_ALLOWED_COMPANY_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}


def _validate_company_image_upload(file: UploadFile) -> str:
    mime_type = file.content_type or ""
    if mime_type not in _ALLOWED_COMPANY_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported image type. Allowed types: PNG, JPEG, GIF, WebP, SVG.",
        )
    return mime_type


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompanySettingsResponse:
    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()
    if company is None:
        # Auto-create a default record on first access
        company = CompanySettings()
        db.add(company)
        await db.flush()
        await db.refresh(company)
    return CompanySettingsResponse.model_validate(company)


@router.patch("/company", response_model=CompanySettingsResponse)
async def update_company_settings(
    body: CompanySettingsUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CompanySettingsResponse:
    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()
    if company is None:
        company = CompanySettings()
        db.add(company)
        await db.flush()

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)

    await db.flush()
    await db.refresh(company)
    return CompanySettingsResponse.model_validate(company)


@router.post("/company/logo", status_code=200)
async def upload_logo(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    file_storage: FileStorageService = Depends(get_file_storage),
) -> dict:
    """Upload company logo image."""
    mime_type = _validate_company_image_upload(file)

    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()
    if company is None:
        company = CompanySettings()
        db.add(company)
        await db.flush()

    try:
        storage_key, sha256, size = file_storage.upload(file.file, file.filename or "logo", mime_type)
    except ValueError as exc:
        status_code = (
            status.HTTP_413_CONTENT_TOO_LARGE
            if "exceeds maximum" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(exc))

    file_record = FileRecord(
        storage_key=storage_key,
        original_filename=file.filename,
        mime_type=mime_type,
        size_bytes=size,
        checksum_sha256=sha256,
        uploaded_by=current_user.id,
        linked_entity_type="company_settings",
        linked_entity_id=company.id,
    )
    db.add(file_record)
    await db.flush()

    company.logo_file_id = file_record.id
    await db.flush()

    return {"logo_file_id": str(file_record.id), "message": "Logo uploaded"}


@router.post("/company/stamp", status_code=200)
async def upload_stamp(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    file_storage: FileStorageService = Depends(get_file_storage),
) -> dict:
    """Upload company stamp/chop image."""
    mime_type = _validate_company_image_upload(file)

    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()
    if company is None:
        company = CompanySettings()
        db.add(company)
        await db.flush()

    try:
        storage_key, sha256, size = file_storage.upload(file.file, file.filename or "stamp", mime_type)
    except ValueError as exc:
        status_code = (
            status.HTTP_413_CONTENT_TOO_LARGE
            if "exceeds maximum" in str(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(exc))

    file_record = FileRecord(
        storage_key=storage_key,
        original_filename=file.filename,
        mime_type=mime_type,
        size_bytes=size,
        checksum_sha256=sha256,
        uploaded_by=current_user.id,
        linked_entity_type="company_settings",
        linked_entity_id=company.id,
    )
    db.add(file_record)
    await db.flush()

    company.stamp_file_id = file_record.id
    await db.flush()

    return {"stamp_file_id": str(file_record.id), "message": "Stamp uploaded"}


@router.get("/company/logo")
async def get_logo_url(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: FileStorageService = Depends(get_file_storage),
) -> dict:
    """Get presigned URL for company logo."""
    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()
    if company is None or company.logo_file_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo uploaded")

    file_result = await db.execute(select(FileRecord).where(FileRecord.id == company.logo_file_id))
    file_record = file_result.scalar_one_or_none()
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo file not found")

    url = file_storage.get_presigned_url(file_record.storage_key)
    return {"url": url, "logo_file_id": str(company.logo_file_id)}


@router.get("/company/stamp")
async def get_stamp_url(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: FileStorageService = Depends(get_file_storage),
) -> dict:
    """Get presigned URL for company stamp."""
    result = await db.execute(select(CompanySettings).limit(1))
    company = result.scalar_one_or_none()
    if company is None or company.stamp_file_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No stamp uploaded")

    file_result = await db.execute(select(FileRecord).where(FileRecord.id == company.stamp_file_id))
    file_record = file_result.scalar_one_or_none()
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stamp file not found")

    url = file_storage.get_presigned_url(file_record.storage_key)
    return {"url": url, "stamp_file_id": str(company.stamp_file_id)}


@router.get("/currencies", response_model=list[CurrencyResponse])
async def list_currencies(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CurrencyResponse]:
    result = await db.execute(
        select(Currency).where(Currency.is_active == True).order_by(Currency.code)
    )
    currencies = result.scalars().all()
    return [CurrencyResponse.model_validate(c) for c in currencies]


@router.post("/currencies", response_model=CurrencyResponse, status_code=status.HTTP_201_CREATED)
async def create_currency(
    body: CurrencyCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("admin:manage_users"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CurrencyResponse:
    # Check for duplicate
    result = await db.execute(select(Currency).where(Currency.code == body.code))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Currency '{body.code}' already exists",
        )

    currency = Currency(
        code=body.code,
        name=body.name,
        symbol=body.symbol,
        display_precision=body.display_precision,
        storage_precision=body.storage_precision,
        is_crypto=body.is_crypto,
        chain_id=body.chain_id,
    )
    db.add(currency)
    await db.flush()
    await db.refresh(currency)
    return CurrencyResponse.model_validate(currency)
