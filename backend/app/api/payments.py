import io
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.file import File
from app.schemas.payment import (
    PaymentCreate,
    PaymentLinkRequest,
    PaymentListResponse,
    PaymentPipelineRequest,
    PaymentPipelineResponse,
    PaymentResponse,
)
from app.services.file_storage import FileStorageService, get_file_storage
from app.schemas.payment_allocation import (
    AllocatePaymentRequest,
    AllocatePaymentResponse,
    AllocationResponse,
)
from app.services import payment as payment_svc
from app.services import payment_allocation as allocation_svc

router = APIRouter()


@router.post("/pipeline", response_model=PaymentPipelineResponse, status_code=status.HTTP_201_CREATED)
async def payment_pipeline(
    data: PaymentPipelineRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentPipelineResponse:
    """Full pipeline: create payment from entity → attach proof → attempt bank match.

    Supported entity types: payroll_run, invoice, loan.
    """
    try:
        payment, matched_tx = await payment_svc.create_and_match_payment(
            db,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            actor_id=current_user.id,
            payment_type=data.payment_type,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    return PaymentPipelineResponse(
        payment=PaymentResponse.model_validate(payment),
        bank_match_tx_id=matched_tx.id if matched_tx else None,
        bank_match_confidence=float(matched_tx.match_confidence) if matched_tx and matched_tx.match_confidence else None,
    )


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_payment(
    data: PaymentCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    try:
        payment = await payment_svc.record_payment(db, data, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return PaymentResponse.model_validate(payment)


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    entity_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> PaymentListResponse:
    items, total = await payment_svc.list_payments(db, entity_type=entity_type, page=page, per_page=per_page)
    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in items],
        total=total,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    try:
        payment = await payment_svc.get_payment(db, payment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return PaymentResponse.model_validate(payment)


@router.post("/{payment_id}/link", response_model=PaymentResponse)
async def link_payment(
    payment_id: uuid.UUID,
    data: PaymentLinkRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    try:
        payment = await payment_svc.link_payment(
            db,
            payment_id=payment_id,
            entity_type=data.related_entity_type,
            entity_id=data.related_entity_id,
            actor_id=current_user.id,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return PaymentResponse.model_validate(payment)


@router.post("/{payment_id}/attach-proof", response_model=PaymentResponse, status_code=status.HTTP_200_OK)
async def attach_proof(
    payment_id: uuid.UUID,
    file: UploadFile,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    file_storage: Annotated[FileStorageService, Depends(get_file_storage)],
) -> PaymentResponse:
    """Upload and attach a proof/evidence file to a payment."""
    try:
        await payment_svc.get_payment(db, payment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    content = await file.read()
    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(content),
        original_filename=file.filename or "proof",
        mime_type=file.content_type or "application/octet-stream",
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=file.filename,
        mime_type=file.content_type,
        size_bytes=size,
        checksum_sha256=sha256,
        uploaded_by=current_user.id,
        linked_entity_type="payment",
        linked_entity_id=payment_id,
    )
    db.add(file_record)
    await db.flush()

    try:
        payment = await payment_svc.attach_proof(db, payment_id, file_record.id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return PaymentResponse.model_validate(payment)


@router.post("/{payment_id}/allocate", response_model=AllocatePaymentResponse, status_code=status.HTTP_201_CREATED)
async def allocate_payment(
    payment_id: uuid.UUID,
    data: AllocatePaymentRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AllocatePaymentResponse:
    try:
        created, unallocated = await allocation_svc.allocate_payment(
            db,
            payment_id=payment_id,
            allocations=data.allocations,
            user_id=current_user.id,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return AllocatePaymentResponse(
        payment_id=payment_id,
        allocations=[AllocationResponse.model_validate(a) for a in created],
        unallocated_amount=unallocated,
    )


@router.get("/{payment_id}/allocations", response_model=list[AllocationResponse])
async def list_payment_allocations(
    payment_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AllocationResponse]:
    allocations = await allocation_svc.get_payment_allocations(db, payment_id)
    return [AllocationResponse.model_validate(a) for a in allocations]


@router.delete("/allocations/{allocation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allocation(
    allocation_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await allocation_svc.deallocate(db, allocation_id=allocation_id, user_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
