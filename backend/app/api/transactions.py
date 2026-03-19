import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.transaction import TransactionCreate, TransactionListResponse, TransactionResponse, TransactionUpdate
from app.services import transaction as transaction_svc

router = APIRouter()


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TransactionResponse:
    try:
        tx = await transaction_svc.create_transaction(db, data, created_by=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return TransactionResponse.model_validate(tx)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    account_id: Optional[uuid.UUID] = None,
    category: Optional[str] = None,
    tx_status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> TransactionListResponse:
    from datetime import date

    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None

    items, total = await transaction_svc.list_transactions(
        db,
        account_id=account_id,
        category=category,
        status=tx_status,
        start_date=start,
        end_date=end,
        page=page,
        per_page=per_page,
    )
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in items],
        total=total,
    )


@router.get("/{tx_id}", response_model=TransactionResponse)
async def get_transaction(
    tx_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TransactionResponse:
    try:
        tx = await transaction_svc.get_transaction(db, tx_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return TransactionResponse.model_validate(tx)


@router.patch("/{tx_id}", response_model=TransactionResponse)
async def update_transaction(
    tx_id: uuid.UUID,
    data: TransactionUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TransactionResponse:
    try:
        tx = await transaction_svc.update_transaction(db, tx_id, data, user_id=current_user.id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return TransactionResponse.model_validate(tx)


@router.post("/{tx_id}/confirm", response_model=TransactionResponse)
async def confirm_transaction(
    tx_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TransactionResponse:
    try:
        tx = await transaction_svc.confirm_transaction(db, tx_id, user_id=current_user.id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return TransactionResponse.model_validate(tx)


@router.post("/{tx_id}/cancel", response_model=TransactionResponse)
async def cancel_transaction(
    tx_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TransactionResponse:
    try:
        tx = await transaction_svc.cancel_transaction(db, tx_id, user_id=current_user.id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return TransactionResponse.model_validate(tx)
