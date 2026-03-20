import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.integrations.capabilities import Capability


class IntegrationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    direction: str
    event_type: str
    provider_event_id: str | None
    payload_json: dict | None
    result_json: dict | None
    status: str
    error_message: str | None
    created_at: datetime


class IntegrationEventListResponse(BaseModel):
    items: list[IntegrationEventResponse]
    total: int


class ProviderCapabilityInfo(BaseModel):
    name: str
    display_name: str
    capabilities: list[Capability]
    configured: bool


class ProviderListResponse(BaseModel):
    providers: list[ProviderCapabilityInfo]
    total: int = 0


class SyncRequest(BaseModel):
    capability: Capability = Capability.SYNC_TRANSACTIONS


class SyncResponse(BaseModel):
    provider: str
    capability: Capability
    inserted: int
    skipped: int
    errors: int


class TestConnectionResponse(BaseModel):
    provider: str
    status: str
    detail: dict[str, Any] | None = None


class FXRateRequest(BaseModel):
    sell_currency: str
    buy_currency: str
    sell_amount: str | None = None
    buy_amount: str | None = None


class FXRateResponse(BaseModel):
    sell_currency: str
    buy_currency: str
    rate: str
    inverse_rate: str | None = None
    valid_until: datetime | None = None


class PaymentLinkRequest(BaseModel):
    amount: str
    currency: str
    reference: str
    metadata: dict[str, Any] | None = None


class PaymentLinkResponse(BaseModel):
    url: str
    provider_id: str
    expires_at: datetime | None = None
