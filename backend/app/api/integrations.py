import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.integrations import get_provider, list_providers
from app.integrations.base import FXRateProvider, PaymentLinkProvider
from app.integrations.capabilities import Capability
from app.models.integration import IntegrationEvent
from app.schemas.integration import (
    FXRateRequest,
    FXRateResponse,
    IntegrationEventListResponse,
    IntegrationEventResponse,
    PaymentLinkRequest,
    PaymentLinkResponse,
    ProviderCapabilityInfo,
    ProviderListResponse,
    SyncRequest,
    SyncResponse,
    TestConnectionResponse,
)
from app.services import integration as integration_svc
from app.services import webhook as webhook_svc

router = APIRouter()


# --- Webhook endpoint (no auth, verified via provider signature) ---

@router.post("/webhooks/{provider}", status_code=status.HTTP_200_OK)
async def receive_webhook(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    body = await request.body()
    headers = dict(request.headers)

    # Import providers to ensure registry is populated
    import app.integrations.providers  # noqa: F401

    try:
        get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    result, http_status = await webhook_svc.process_webhook(db, provider, body, headers)

    if http_status == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=result.get("error"))
    if http_status != status.HTTP_200_OK:
        return JSONResponse(status_code=http_status, content=result)

    return result


# --- Integration management endpoints ---

@router.get("/integrations", response_model=ProviderListResponse)
async def list_integrations(
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:read"))],
) -> ProviderListResponse:
    import app.integrations.providers  # noqa: F401

    providers = []
    for p in list_providers():
        from app.config import settings

        configured = False
        if p.name == "airwallex":
            configured = bool(settings.AIRWALLEX_CLIENT_ID and settings.AIRWALLEX_API_KEY)

        providers.append(
            ProviderCapabilityInfo(
                name=p.name,
                display_name=p.display_name,
                capabilities=list(p.capabilities),
                configured=configured,
            )
        )

    return ProviderListResponse(providers=providers, total=len(providers))


@router.get("/integrations/{provider}", response_model=ProviderCapabilityInfo)
async def get_integration(
    provider: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:read"))],
) -> ProviderCapabilityInfo:
    import app.integrations.providers  # noqa: F401

    try:
        p = get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    from app.config import settings

    configured = False
    if p.name == "airwallex":
        configured = bool(settings.AIRWALLEX_CLIENT_ID and settings.AIRWALLEX_API_KEY)

    return ProviderCapabilityInfo(
        name=p.name,
        display_name=p.display_name,
        capabilities=list(p.capabilities),
        configured=configured,
    )


@router.post("/integrations/{provider}/test", response_model=TestConnectionResponse)
async def test_integration(
    provider: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:write"))],
) -> TestConnectionResponse:
    import app.integrations.providers  # noqa: F401

    try:
        p = get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    detail = await p.test_connection()
    return TestConnectionResponse(
        provider=provider,
        status=detail.get("status", "unknown"),
        detail=detail,
    )


@router.post("/integrations/{provider}/sync", response_model=SyncResponse)
async def trigger_sync(
    provider: str,
    data: SyncRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SyncResponse:
    import app.integrations.providers  # noqa: F401

    try:
        get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    try:
        result = await integration_svc.run_sync(db, provider, data.capability)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return SyncResponse(
        provider=provider,
        capability=data.capability,
        inserted=result.get("inserted", 0),
        skipped=result.get("skipped", 0),
        errors=result.get("errors", 0),
    )


@router.post("/integrations/{provider}/fx-rate", response_model=FXRateResponse)
async def get_fx_rate(
    provider: str,
    data: FXRateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:read"))],
) -> FXRateResponse:
    import app.integrations.providers  # noqa: F401

    try:
        p = get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    if not isinstance(p, FXRateProvider):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{provider} does not support FX rates")

    result = await p.fetch_fx_rate(
        sell_currency=data.sell_currency,
        buy_currency=data.buy_currency,
        sell_amount=data.sell_amount,
        buy_amount=data.buy_amount,
    )
    return FXRateResponse(
        sell_currency=result.sell_currency,
        buy_currency=result.buy_currency,
        rate=str(result.rate),
        inverse_rate=str(result.inverse_rate) if result.inverse_rate else None,
        valid_until=result.valid_until,
    )


@router.post("/integrations/{provider}/payment-link", response_model=PaymentLinkResponse)
async def create_payment_link(
    provider: str,
    data: PaymentLinkRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:write"))],
) -> PaymentLinkResponse:
    import app.integrations.providers  # noqa: F401

    try:
        p = get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    if not isinstance(p, PaymentLinkProvider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{provider} does not support payment links"
        )

    result = await p.create_payment_link(
        amount=data.amount,
        currency=data.currency,
        reference=data.reference,
        metadata=data.metadata,
    )
    return PaymentLinkResponse(
        url=result.url,
        provider_id=result.provider_id,
        expires_at=result.expires_at,
    )


@router.get("/integrations/{provider}/events", response_model=IntegrationEventListResponse)
async def list_integration_events(
    provider: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_permission("integration:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> IntegrationEventListResponse:
    import app.integrations.providers  # noqa: F401

    try:
        get_provider(provider)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown provider: {provider}")

    query = select(IntegrationEvent).where(IntegrationEvent.provider == provider)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = (
        query.order_by(IntegrationEvent.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return IntegrationEventListResponse(
        items=[IntegrationEventResponse.model_validate(e) for e in items],
        total=total,
    )
