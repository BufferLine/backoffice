import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.file import File
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceUpdate,
    LineItemCreate,
    LineItemResponse,
    LineItemUpdate,
    MarkPaidRequest,
)
from app.services import invoice as invoice_service
from app.services.file_storage import FileStorageService, get_file_storage
from app.state_machines import InvalidTransitionError

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: InvoiceCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoiceResponse:
    invoice = await invoice_service.create_invoice(
        db=db,
        client_id=body.client_id,
        currency=body.currency,
        description=body.description,
        payment_method=body.payment_method,
        wallet_address=body.wallet_address,
        created_by=current_user.id,
        tax_inclusive=body.tax_inclusive,
    )
    return InvoiceResponse.model_validate(invoice)


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    invoice_status: Optional[str] = None,
    client_id: Optional[uuid.UUID] = None,
    page: int = 1,
    per_page: int = 20,
) -> InvoiceListResponse:
    invoices, total = await invoice_service.list_invoices(
        db=db,
        status=invoice_status,
        client_id=client_id,
        page=page,
        per_page=per_page,
    )
    return InvoiceListResponse(
        items=[InvoiceResponse.model_validate(inv) for inv in invoices],
        total=total,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoiceResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()
    return InvoiceResponse.model_validate(invoice)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoiceResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        invoice = await invoice_service.update_invoice(
            db=db,
            invoice=invoice,
            description=body.description,
            currency=body.currency,
            payment_method=body.payment_method,
            wallet_address=body.wallet_address,
            tax_inclusive=body.tax_inclusive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return InvoiceResponse.model_validate(invoice)


@router.post("/{invoice_id}/line-items", response_model=LineItemResponse, status_code=status.HTTP_201_CREATED)
async def add_line_item(
    invoice_id: uuid.UUID,
    body: LineItemCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LineItemResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        item = await invoice_service.add_line_item(
            db=db,
            invoice=invoice,
            description=body.description,
            quantity=body.quantity,
            unit_price=body.unit_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return LineItemResponse.model_validate(item)


@router.patch("/{invoice_id}/line-items/{item_id}", response_model=LineItemResponse)
async def update_line_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    body: LineItemUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LineItemResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        item = await invoice_service.update_line_item(
            db=db,
            invoice=invoice,
            item_id=item_id,
            description=body.description,
            quantity=body.quantity,
            unit_price=body.unit_price,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")

    return LineItemResponse.model_validate(item)


@router.delete("/{invoice_id}/line-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        deleted = await invoice_service.delete_line_item(db=db, invoice=invoice, item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")


@router.post("/{invoice_id}/issue", response_model=InvoiceResponse)
async def issue_invoice(
    invoice_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> InvoiceResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        invoice = await invoice_service.issue_invoice(
            db=db,
            invoice=invoice,
            user_id=current_user.id,
            file_storage=file_storage,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return InvoiceResponse.model_validate(invoice)


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
async def mark_paid(
    invoice_id: uuid.UUID,
    body: MarkPaidRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoiceResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        invoice = await invoice_service.mark_paid(
            db=db,
            invoice=invoice,
            payment_id=body.payment_id,
            user_id=current_user.id,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return InvoiceResponse.model_validate(invoice)


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvoiceResponse:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    try:
        invoice = await invoice_service.cancel_invoice(
            db=db,
            invoice=invoice,
            user_id=current_user.id,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return InvoiceResponse.model_validate(invoice)


@router.post("/{invoice_id}/attach-file", response_model=dict, status_code=status.HTTP_201_CREATED)
async def attach_file(
    invoice_id: uuid.UUID,
    file: UploadFile,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> dict:
    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise _not_found()

    content = await file.read()
    import io
    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(content),
        original_filename=file.filename or "attachment",
        mime_type=file.content_type or "application/octet-stream",
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=file.filename,
        mime_type=file.content_type,
        size_bytes=size,
        checksum_sha256=sha256,
        uploaded_by=current_user.id,
        linked_entity_type="invoice",
        linked_entity_id=invoice_id,
    )
    db.add(file_record)
    await db.flush()
    await db.refresh(file_record)

    return {"file_id": str(file_record.id), "storage_key": storage_key}
