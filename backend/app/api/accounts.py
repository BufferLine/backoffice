import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.account import AccountBalanceResponse, AccountCreate, AccountListResponse, AccountResponse, AccountUpdate
from app.schemas.transaction import TransactionListResponse, TransactionResponse
from app.services import account as account_svc
from app.services import transaction as transaction_svc

router = APIRouter()


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: AccountCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountResponse:
    account = await account_svc.create_account(db, data, created_by=current_user.id)
    return AccountResponse.model_validate(account)


@router.get("", response_model=AccountListResponse)
async def list_accounts(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    per_page: int = 20,
    include_inactive: bool = False,
) -> AccountListResponse:
    items, total = await account_svc.list_accounts(db, page=page, per_page=per_page, include_inactive=include_inactive)
    return AccountListResponse(
        items=[AccountResponse.model_validate(a) for a in items],
        total=total,
    )


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountResponse:
    try:
        account = await account_svc.get_account(db, account_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    data: AccountUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountResponse:
    try:
        account = await account_svc.update_account(db, account_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return AccountResponse.model_validate(account)


@router.get("/{account_id}/balance", response_model=AccountBalanceResponse)
async def get_account_balance(
    account_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountBalanceResponse:
    try:
        balance = await account_svc.get_balance(db, account_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return balance


@router.get("/{account_id}/transactions", response_model=TransactionListResponse)
async def list_account_transactions(
    account_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
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
