from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.schemas.ledger import LedgerAccountsResponse, LedgerAccountsUpdate
from app.services import ledger as ledger_svc

router = APIRouter()


def _response(mapping: ledger_svc.LedgerAccounts) -> LedgerAccountsResponse:
    return LedgerAccountsResponse(
        receivable=mapping.receivable,
        revenue=mapping.revenue,
        gst_output=mapping.gst_output,
        fx_gain_loss=mapping.fx_gain_loss,
        configured=mapping.configured,
    )


@router.get("/accounts", response_model=LedgerAccountsResponse)
async def get_ledger_accounts(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("journal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LedgerAccountsResponse:
    return _response(await ledger_svc.get_ledger_accounts(db))


@router.patch("/accounts", response_model=LedgerAccountsResponse)
async def update_ledger_accounts(
    data: LedgerAccountsUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("journal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LedgerAccountsResponse:
    try:
        mapping = await ledger_svc.set_ledger_accounts(
            db,
            actor_id=current_user.id,
            receivable=data.receivable,
            revenue=data.revenue,
            gst_output=data.gst_output,
            fx_gain_loss=data.fx_gain_loss,
        )
    except ValueError as e:
        detail = str(e)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=detail)
    return _response(mapping)
