from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.database import get_db
from app.schemas.journal import (
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    TrialBalanceResponse,
)
from app.services import journal as journal_svc

router = APIRouter()


@router.post("", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    data: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("journal:write")),
):
    entry = await journal_svc.create_journal_entry(db, data, created_by=user["user_id"])
    return entry


@router.get("", response_model=JournalEntryListResponse)
async def list_journal_entries(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    confirmed: Optional[bool] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("journal:read")),
):
    items, total = await journal_svc.list_journal_entries(
        db, page=page, per_page=per_page,
        confirmed_only=confirmed, from_date=from_date, to_date=to_date,
    )
    return JournalEntryListResponse(items=items, total=total)


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    as_of: Optional[date] = None,
    confirmed_only: bool = True,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("journal:read")),
):
    return await journal_svc.get_trial_balance(db, as_of=as_of, confirmed_only=confirmed_only)


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("journal:read")),
):
    try:
        return await journal_svc.get_journal_entry(db, entry_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Journal entry not found")


@router.post("/{entry_id}/confirm", response_model=JournalEntryResponse)
async def confirm_journal_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("journal:write")),
):
    try:
        return await journal_svc.confirm_journal_entry(db, entry_id, confirmed_by=user["user_id"])
    except ValueError:
        raise HTTPException(status_code=404, detail="Journal entry not found")


@router.delete("/{entry_id}", status_code=204)
async def delete_journal_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_permission("journal:write")),
):
    try:
        await journal_svc.delete_journal_entry(db, entry_id)
    except ValueError as e:
        if "confirmed" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
