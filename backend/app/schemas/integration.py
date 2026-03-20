import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


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
    capabilities: list[str]
    configured: bool


class ProviderListResponse(BaseModel):
    providers: list[ProviderCapabilityInfo]


class SyncRequest(BaseModel):
    capability: str = "sync_transactions"


class SyncResponse(BaseModel):
    provider: str
    capability: str
    inserted: int
    skipped: int
    errors: int


class TestConnectionResponse(BaseModel):
    provider: str
    status: str
    detail: dict[str, Any] | None = None
