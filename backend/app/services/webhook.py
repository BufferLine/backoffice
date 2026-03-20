"""Webhook processing service."""
import logging
import uuid
from typing import Any

from fastapi import Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import get_provider
from app.integrations.base import WebhookProvider
from app.integrations.exceptions import WebhookSignatureError
from app.models.integration import IntegrationEvent

logger = logging.getLogger(__name__)


async def process_webhook(
    db: AsyncSession,
    provider_name: str,
    body: bytes,
    headers: dict[str, str],
) -> tuple[dict[str, Any], int]:
    """
    Verify, deduplicate, log, and process an inbound webhook.

    Returns (response_body, http_status_code).
    Returns 401 on signature failure.
    Returns 200 for duplicates (idempotent) and successful processing.
    """
    provider = get_provider(provider_name)

    if not isinstance(provider, WebhookProvider):
        return {"error": f"Provider {provider_name!r} does not support webhooks"}, status.HTTP_400_BAD_REQUEST

    # --- Verify signature ---
    try:
        provider.verify_webhook(body, headers)
    except WebhookSignatureError as exc:
        logger.warning("Webhook signature failure for %s: %s", provider_name, exc)
        return {"error": "Invalid webhook signature"}, status.HTTP_401_UNAUTHORIZED

    # --- Parse event ---
    try:
        event = provider.parse_webhook(body, headers)
    except Exception as exc:
        logger.exception("Failed to parse webhook for %s", provider_name)
        return {"error": f"Failed to parse webhook: {exc}"}, status.HTTP_400_BAD_REQUEST

    # --- Idempotency check via (provider, provider_event_id) ---
    if event.event_id:
        result = await db.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.provider == provider_name,
                IntegrationEvent.provider_event_id == event.event_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.info(
                "Duplicate webhook event %s/%s — skipping",
                provider_name,
                event.event_id,
            )
            return {"status": "duplicate", "event_id": event.event_id}, status.HTTP_200_OK

    # --- Log event ---
    db_event = IntegrationEvent(
        provider=provider_name,
        direction="inbound",
        event_type=event.event_type,
        provider_event_id=event.event_id or None,
        payload_json=event.payload,
        status="processing",
    )
    db.add(db_event)
    await db.flush()

    # --- Handle event ---
    try:
        result_data = await provider.handle_event(event)
        db_event.status = "processed"
        db_event.result_json = result_data
    except Exception as exc:
        logger.exception(
            "Error handling webhook event %s/%s", provider_name, event.event_id
        )
        db_event.status = "failed"
        db_event.error_message = str(exc)
        result_data = {"error": str(exc)}

    await db.flush()

    return {"status": db_event.status, "event_id": event.event_id, "result": result_data}, status.HTTP_200_OK
