import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.integrations import register_provider
from app.integrations.base import (
    BalanceSyncProvider,
    FXRateProvider,
    IntegrationProvider,
    PaymentLinkProvider,
    TransactionSyncProvider,
    TransferProvider,
    WebhookProvider,
)
from app.integrations.capabilities import (
    BalanceInfo,
    FXRate,
    PaymentLinkResult,
    SyncedTransaction,
    TransferResult,
    WebhookEvent,
)
from app.integrations.exceptions import (
    ProviderAPIError,
    ProviderRateLimitError,
    WebhookSignatureError,
)

logger = logging.getLogger(__name__)


class AirwallexProvider(
    IntegrationProvider,
    TransactionSyncProvider,
    BalanceSyncProvider,
    WebhookProvider,
    TransferProvider,
    FXRateProvider,
    PaymentLinkProvider,
):
    """Airwallex integration provider."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def name(self) -> str:
        return "airwallex"

    @property
    def display_name(self) -> str:
        return "Airwallex"

    # --- Auth ---

    async def _get_token(self) -> str:
        """Return cached bearer token, refreshing if expired or missing."""
        now = time.time()
        # Refresh if token is missing or within 60s of expiry
        if self._token is None or now >= self._token_expires_at - 60:
            await self._refresh_token()
        if self._token is None:
            raise ProviderAPIError(self.name, 0, "Authentication did not return a bearer token")
        return self._token

    async def _refresh_token(self) -> None:
        if not settings.AIRWALLEX_CLIENT_ID or not settings.AIRWALLEX_API_KEY:
            raise ProviderAPIError(
                self.name,
                0,
                "AIRWALLEX_CLIENT_ID and AIRWALLEX_API_KEY must be configured",
            )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.AIRWALLEX_BASE_URL}/api/v1/authentication/login",
                headers={
                    "x-client-id": settings.AIRWALLEX_CLIENT_ID,
                    "x-api-key": settings.AIRWALLEX_API_KEY,
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code not in (200, 201):
            raise ProviderAPIError(self.name, resp.status_code, resp.text)
        data = resp.json()
        self._token = data["token"]
        # Token is valid for 30 minutes; store expiry as unix timestamp
        self._token_expires_at = time.time() + 30 * 60

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Make an authenticated request; retry once on 401."""
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method,
                f"{settings.AIRWALLEX_BASE_URL}{path}",
                headers=headers,
                **kwargs,
            )

        if resp.status_code == 401:
            # Token may have been invalidated; refresh and retry once
            await self._refresh_token()
            headers["Authorization"] = f"Bearer {self._token}"
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method,
                    f"{settings.AIRWALLEX_BASE_URL}{path}",
                    headers=headers,
                    **kwargs,
                )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            raise ProviderRateLimitError(self.name, 429, "Rate limited", retry_after=retry_after)

        if resp.status_code >= 400:
            raise ProviderAPIError(self.name, resp.status_code, resp.text)

        return resp.json()

    async def test_connection(self) -> dict[str, Any]:
        try:
            await self._get_token()
            return {"status": "ok", "provider": self.name}
        except ProviderAPIError as e:
            return {"status": "error", "provider": self.name, "error": str(e)}

    # --- TransactionSyncProvider ---

    async def sync_transactions(
        self,
        since: str | None = None,
        cursor: str | None = None,
    ) -> tuple[list[SyncedTransaction], str | None]:
        params: dict[str, Any] = {"page_size": 100}
        if since:
            params["from_created_at"] = since
        if cursor:
            params["page_num"] = cursor

        data = await self._request("GET", "/api/v1/financial_transactions", params=params)

        items = data.get("items", [])
        has_more = data.get("has_more", False)
        next_cursor: str | None = None
        if has_more:
            next_page = data.get("page_num", 0) + 1
            next_cursor = str(next_page)

        transactions: list[SyncedTransaction] = []
        for item in items:
            tx_date_str = item.get("transaction_date") or item.get("created_at", "")
            try:
                tx_date = datetime.fromisoformat(tx_date_str.replace("Z", "+00:00")).date()
            except (ValueError, AttributeError):
                continue

            transactions.append(
                SyncedTransaction(
                    source_tx_id=item.get("id") or item.get("financial_transaction_id", ""),
                    tx_date=tx_date,
                    amount=Decimal(str(item.get("amount", "0"))),
                    currency=item.get("currency", "USD"),
                    counterparty=item.get("account_name"),
                    reference=item.get("source_id") or item.get("batch_booking_id"),
                    description=item.get("description") or item.get("transaction_type"),
                    raw_data=item,
                )
            )

        return transactions, next_cursor

    # --- BalanceSyncProvider ---

    async def sync_balances(self) -> list[BalanceInfo]:
        data = await self._request("GET", "/api/v1/balances/current")
        balances: list[BalanceInfo] = []
        for item in data if isinstance(data, list) else [data]:
            currency = item.get("currency", "USD")
            available = Decimal(str(item.get("available_amount", "0")))
            pending_raw = item.get("pending_amount")
            pending = Decimal(str(pending_raw)) if pending_raw is not None else None
            balances.append(
                BalanceInfo(
                    currency=currency,
                    available_balance=available,
                    pending_balance=pending,
                    as_of=datetime.now(timezone.utc),
                )
            )
        return balances

    # --- WebhookProvider ---

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> None:
        secret = settings.AIRWALLEX_WEBHOOK_SECRET
        if not secret:
            raise WebhookSignatureError("AIRWALLEX_WEBHOOK_SECRET is not configured")

        sig_header = headers.get("x-signature") or headers.get("X-Signature")
        if not sig_header:
            raise WebhookSignatureError("Missing X-Signature header")

        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, sig_header):
            raise WebhookSignatureError("Webhook signature verification failed")

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        payload = json.loads(body)
        event_type = payload.get("name", "unknown")
        event_id = payload.get("id", "")
        timestamp_str = payload.get("created_at")
        timestamp: datetime | None = None
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        return WebhookEvent(
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            timestamp=timestamp,
        )

    async def handle_event(self, event: WebhookEvent) -> dict[str, Any]:
        logger.info("Handling Airwallex event: %s (id=%s)", event.event_type, event.event_id)
        handler = {
            "financial_transaction.created": self._handle_transaction_created,
            "payment_attempt.settled": self._handle_payment_settled,
            "payout.completed": self._handle_payout_completed,
            "payout.failed": self._handle_payout_failed,
        }.get(event.event_type)

        if handler:
            return await handler(event)
        return {"action": "ignored", "event_type": event.event_type}

    async def _handle_transaction_created(self, event: WebhookEvent) -> dict[str, Any]:
        return {"action": "transaction_created", "event_id": event.event_id}

    async def _handle_payment_settled(self, event: WebhookEvent) -> dict[str, Any]:
        return {"action": "payment_settled", "event_id": event.event_id}

    async def _handle_payout_completed(self, event: WebhookEvent) -> dict[str, Any]:
        return {"action": "payout_completed", "event_id": event.event_id}

    async def _handle_payout_failed(self, event: WebhookEvent) -> dict[str, Any]:
        return {"action": "payout_failed", "event_id": event.event_id}

    # --- FXRateProvider ---

    async def fetch_fx_rate(
        self,
        sell_currency: str,
        buy_currency: str,
        sell_amount: str | None = None,
        buy_amount: str | None = None,
    ) -> FXRate:
        params: dict[str, Any] = {
            "sell_currency": sell_currency,
            "buy_currency": buy_currency,
        }
        if sell_amount:
            params["sell_amount"] = sell_amount
        if buy_amount:
            params["buy_amount"] = buy_amount

        data = await self._request("GET", "/api/v1/fx/rates/current", params=params)

        rate = Decimal(str(data.get("client_rate", data.get("rate", "0"))))
        inverse = data.get("inverse_rate")
        inverse_rate = Decimal(str(inverse)) if inverse else None

        valid_until: datetime | None = None
        expiry_str = data.get("valid_to") or data.get("rate_expiry")
        if expiry_str:
            try:
                valid_until = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        return FXRate(
            sell_currency=sell_currency,
            buy_currency=buy_currency,
            rate=rate,
            inverse_rate=inverse_rate,
            valid_until=valid_until,
            raw_data=data,
        )

    # --- PaymentLinkProvider ---

    async def create_payment_link(
        self,
        amount: str,
        currency: str,
        reference: str,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentLinkResult:
        payload: dict[str, Any] = {
            "amount": float(amount),
            "currency": currency,
            "title": reference,
            "reusable": False,
        }
        if metadata:
            payload["metadata"] = metadata

        data = await self._request("POST", "/api/v1/pa/payment_links/create", json=payload)

        expires_at: datetime | None = None
        expiry_str = data.get("expires_at")
        if expiry_str:
            try:
                expires_at = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        return PaymentLinkResult(
            url=data["url"],
            provider_id=data["id"],
            expires_at=expires_at,
        )

    # --- TransferProvider ---

    async def initiate_transfer(
        self,
        amount: str,
        currency: str,
        destination: dict[str, Any],
        reference: str | None = None,
    ) -> TransferResult:
        payload: dict[str, Any] = {
            "amount": float(amount),
            "currency": currency,
            "beneficiary": destination,
        }
        if reference:
            payload["reference"] = reference

        data = await self._request("POST", "/api/v1/payments/create", json=payload)
        return TransferResult(
            provider_transfer_id=data["id"],
            status=data.get("status", "created"),
            reference=data.get("reference"),
        )


# Register a singleton instance
register_provider(AirwallexProvider())
