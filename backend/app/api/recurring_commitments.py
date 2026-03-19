import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.recurring_commitment import (
    RecurringCommitmentCreate,
    RecurringCommitmentListResponse,
    RecurringCommitmentResponse,
    RecurringCommitmentUpdate,
)
from app.schemas.transaction import TransactionListResponse, TransactionResponse
from app.services import recurring_commitment as commitment_svc

router = APIRouter()


@router.post("", response_model=RecurringCommitmentResponse, status_code=status.HTTP_201_CREATED)
async def create_commitment(
    data: RecurringCommitmentCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecurringCommitmentResponse:
    commitment = await commitment_svc.create_commitment(db, data, created_by=current_user.id)
    return RecurringCommitmentResponse.model_validate(commitment)


@router.get("", response_model=RecurringCommitmentListResponse)
async def list_commitments(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    per_page: int = 20,
) -> RecurringCommitmentListResponse:
    items, total = await commitment_svc.list_commitments(db, page=page, per_page=per_page)
    return RecurringCommitmentListResponse(
        items=[RecurringCommitmentResponse.model_validate(c) for c in items],
        total=total,
    )


@router.get("/{commitment_id}", response_model=RecurringCommitmentResponse)
async def get_commitment(
    commitment_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecurringCommitmentResponse:
    try:
        commitment = await commitment_svc.get_commitment(db, commitment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return RecurringCommitmentResponse.model_validate(commitment)


@router.patch("/{commitment_id}", response_model=RecurringCommitmentResponse)
async def update_commitment(
    commitment_id: uuid.UUID,
    data: RecurringCommitmentUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecurringCommitmentResponse:
    try:
        commitment = await commitment_svc.update_commitment(db, commitment_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return RecurringCommitmentResponse.model_validate(commitment)


@router.delete("/{commitment_id}", response_model=RecurringCommitmentResponse)
async def deactivate_commitment(
    commitment_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecurringCommitmentResponse:
    try:
        commitment = await commitment_svc.deactivate_commitment(db, commitment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return RecurringCommitmentResponse.model_validate(commitment)


@router.post("/generate-pending", response_model=TransactionListResponse)
async def generate_pending(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: str = "",
) -> TransactionListResponse:
    if not month:
        from datetime import date
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    try:
        txs = await commitment_svc.generate_pending_transactions(db, month, created_by=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in txs],
        total=len(txs),
    )
