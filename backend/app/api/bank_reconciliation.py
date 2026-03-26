import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.bank import (
    AutoMatchResult,
    BankTransactionListResponse,
    BankTransactionResponse,
    BankTxMatchRequest,
    BankTxReconcileRequest,
)
from app.services import bank_reconciliation as bank_svc

router = APIRouter()


@router.post("/bank-statements/upload", status_code=status.HTTP_201_CREATED)
async def upload_bank_statement(
    file: UploadFile,
    source: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    original_filename = file.filename or "statement.csv"
    mime_type = file.content_type or "text/csv"

    try:
        summary = await bank_svc.import_statement(
            db=db,
            file_data=file.file,
            source=source,
            filename=original_filename,
            user_id=current_user.id,
            mime_type=mime_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return summary


@router.get("/bank-transactions", response_model=BankTransactionListResponse)
async def list_bank_transactions(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    match_status: Optional[str] = None,
    source: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> BankTransactionListResponse:
    items, total = await bank_svc.list_transactions(
        db, status=match_status, source=source, page=page, per_page=per_page
    )
    return BankTransactionListResponse(
        items=[BankTransactionResponse.model_validate(t) for t in items],
        total=total,
    )


# Literal route must be declared before parameterized /{tx_id} routes
@router.post("/bank-transactions/auto-match", response_model=AutoMatchResult)
async def auto_match_transactions(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutoMatchResult:
    return await bank_svc.auto_match(db)


@router.get("/bank-transactions/{tx_id}", response_model=BankTransactionResponse)
async def get_bank_transaction(
    tx_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BankTransactionResponse:
    try:
        tx = await bank_svc.get_transaction(db, tx_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return BankTransactionResponse.model_validate(tx)


@router.post("/bank-transactions/{tx_id}/match", response_model=BankTransactionResponse)
async def match_bank_transaction(
    tx_id: uuid.UUID,
    data: BankTxMatchRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BankTransactionResponse:
    try:
        tx = await bank_svc.manual_match(db, tx_id, data.payment_id, current_user.id)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return BankTransactionResponse.model_validate(tx)


@router.post("/bank-transactions/{tx_id}/reconcile", response_model=BankTransactionResponse)
async def reconcile_bank_transaction(
    tx_id: uuid.UUID,
    data: BankTxReconcileRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BankTransactionResponse:
    try:
        tx = await bank_svc.reconcile_transaction(
            db, tx_id,
            bank_account_id=data.bank_account_id,
            contra_account_id=data.contra_account_id,
            actor_id=current_user.id,
            description=data.description,
            auto_confirm=data.auto_confirm,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return BankTransactionResponse.model_validate(tx)


@router.post("/bank-transactions/{tx_id}/ignore", response_model=BankTransactionResponse)
async def ignore_bank_transaction(
    tx_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BankTransactionResponse:
    try:
        tx = await bank_svc.ignore_transaction(db, tx_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return BankTransactionResponse.model_validate(tx)
