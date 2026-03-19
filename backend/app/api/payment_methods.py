import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.payment_method import PaymentMethod
from app.schemas.payment_method import PaymentMethodCreate, PaymentMethodResponse, PaymentMethodUpdate

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment method not found")


@router.post("", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_method(
    body: PaymentMethodCreate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentMethodResponse:
    if body.is_default:
        # Unset existing defaults for the same currency
        await db.execute(
            update(PaymentMethod)
            .where(PaymentMethod.currency == body.currency, PaymentMethod.is_default == True)
            .values(is_default=False)
        )

    method = PaymentMethod(
        name=body.name,
        nickname=body.nickname,
        type=body.type,
        currency=body.currency,
        bank_name=body.bank_name,
        bank_account_number=body.bank_account_number,
        bank_swift_code=body.bank_swift_code,
        wallet_address=body.wallet_address,
        chain_id=body.chain_id,
        uen_number=body.uen_number,
        is_default=body.is_default or False,
        is_active=True,
        created_by=current_user.id,
    )
    db.add(method)
    await db.flush()
    await db.refresh(method)
    return PaymentMethodResponse.model_validate(method)


@router.get("", response_model=list[PaymentMethodResponse])
async def list_payment_methods(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PaymentMethodResponse]:
    result = await db.execute(
        select(PaymentMethod)
        .where(PaymentMethod.is_active == True)
        .order_by(PaymentMethod.currency, PaymentMethod.name)
    )
    methods = result.scalars().all()
    return [PaymentMethodResponse.model_validate(m) for m in methods]


@router.get("/{method_id}", response_model=PaymentMethodResponse)
async def get_payment_method(
    method_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("invoice:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentMethodResponse:
    result = await db.execute(select(PaymentMethod).where(PaymentMethod.id == method_id))
    method = result.scalar_one_or_none()
    if method is None:
        raise _not_found()
    return PaymentMethodResponse.model_validate(method)


@router.patch("/{method_id}", response_model=PaymentMethodResponse)
async def update_payment_method(
    method_id: uuid.UUID,
    body: PaymentMethodUpdate,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentMethodResponse:
    result = await db.execute(select(PaymentMethod).where(PaymentMethod.id == method_id))
    method = result.scalar_one_or_none()
    if method is None:
        raise _not_found()

    update_data = body.model_dump(exclude_unset=True)

    # If setting as default, unset other defaults for this currency
    if update_data.get("is_default"):
        currency = update_data.get("currency", method.currency)
        await db.execute(
            update(PaymentMethod)
            .where(
                PaymentMethod.currency == currency,
                PaymentMethod.is_default == True,
                PaymentMethod.id != method_id,
            )
            .values(is_default=False)
        )

    for field, value in update_data.items():
        setattr(method, field, value)

    await db.flush()
    await db.refresh(method)
    return PaymentMethodResponse.model_validate(method)


@router.delete("/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    method_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("payment:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(select(PaymentMethod).where(PaymentMethod.id == method_id))
    method = result.scalar_one_or_none()
    if method is None:
        raise _not_found()

    method.is_active = False
    await db.flush()
