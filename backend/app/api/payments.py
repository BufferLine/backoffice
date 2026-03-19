import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.payment import PaymentCreate, PaymentLinkRequest, PaymentListResponse, PaymentResponse
from app.services import payment as payment_svc

router = APIRouter()


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
