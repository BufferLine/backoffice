from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, get_current_user, require_permission
from app.database import get_db
from app.models.company import CompanySettings
from app.models.currency import Currency
from app.schemas.company import (
    CompanySettingsResponse,
    CompanySettingsUpdate,
    CurrencyCreate,
    CurrencyResponse,
)

router = APIRouter()


@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings(
    current_user: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
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
    current_user: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
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
    current_user: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
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
