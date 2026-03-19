import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.client import Client
from app.schemas.invoice import ClientCreate, ClientResponse, ClientUpdate

router = APIRouter()


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate,
    current_user: Annotated[AuthenticatedUser, require_permission("invoice:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientResponse:
    client = Client(
        legal_name=body.legal_name,
        billing_email=body.billing_email,
        billing_address=body.billing_address,
        default_currency=body.default_currency,
        payment_terms_days=body.payment_terms_days,
        preferred_payment_method=body.preferred_payment_method,
        wallet_address=body.wallet_address,
    )
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return ClientResponse.model_validate(client)


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    current_user: Annotated[AuthenticatedUser, require_permission("invoice:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ClientResponse]:
    result = await db.execute(
        select(Client).where(Client.is_active == True).order_by(Client.legal_name)
    )
    clients = result.scalars().all()
    return [ClientResponse.model_validate(c) for c in clients]


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, require_permission("invoice:read")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientResponse:
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ClientResponse.model_validate(client)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    body: ClientUpdate,
    current_user: Annotated[AuthenticatedUser, require_permission("invoice:write")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientResponse:
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    await db.flush()
    await db.refresh(client)
    return ClientResponse.model_validate(client)
