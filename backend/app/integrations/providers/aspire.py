"""Aspire (aspireapp.com) integration provider.

API reference: https://docs.api.aspireapp.com/api (OpenAPI spec at /api/v1.yaml).

Notes on the Aspire API that shape this implementation:
- Auth: ``POST /login`` with client_credentials returns a bearer token valid for
  ``expires_in`` seconds (900 by default). There is no refresh token for API keys.
- Amounts (``amount``, ``balance``, ``available_balance``) are integers in the
  currency's minor unit (e.g. 135000 = SGD 1,350.00). Debits are negative.
- ``GET /transactions`` requires ``start_date`` (``YYYY-MM-DDTHH:mm:ssZ``) and is
  page-based (``page`` query param, ``metadata.next_page_url``).
- Rate limit: < 100 RPM per GET endpoint; 429 on breach.
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.integrations import register_provider
from app.integrations.base import (
    BalanceSyncProvider,
    IntegrationProvider,
    TransactionSyncProvider,
)
from app.integrations.capabilities import BalanceInfo, SyncedTransaction
from app.integrations.exceptions import ProviderAPIError, ProviderRateLimitError

logger = logging.getLogger(__name__)

# Bank statements are dated in Singapore local time; Aspire returns UTC timestamps.
_LOCAL_TZ = ZoneInfo("Asia/Singapore")

# ISO 4217 minor-unit exponents that differ from the default of 2.
# Aspire documents IDR as having no minor unit.
_ZERO_DECIMAL_CURRENCIES = {
    "BIF", "CLP", "DJF", "GNF", "IDR", "ISK", "JPY", "KMF", "KRW", "PYG",
    "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}
_THREE_DECIMAL_CURRENCIES = {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}

# Card transactions that have not settled yet; amounts may still change.
_SKIP_STATUSES = {"pending"}

_SYNC_OVERLAP = timedelta(days=7)

# How long the list of operating (debit) account IDs is reused between calls.
_ACCOUNTS_CACHE_TTL = 600.0


def from_minor_units(value: Any, currency: str) -> Decimal:
    """Convert an Aspire integer minor-unit amount to a Decimal in major units."""
    if value is None:
        return Decimal("0")
    currency = (currency or "").upper()
    if currency in _ZERO_DECIMAL_CURRENCIES:
        exponent = 0
    elif currency in _THREE_DECIMAL_CURRENCIES:
        exponent = 3
    else:
        exponent = 2
    return Decimal(str(value)).scaleb(-exponent)


def _to_aspire_timestamp(value: str | None) -> str:
    """Normalise an ISO-8601 timestamp to Aspire's ``YYYY-MM-DDTHH:mm:ssZ`` (UTC).

    Falls back to ``ASPIRE_SYNC_LOOKBACK_DAYS`` ago when no value is given,
    because Aspire requires ``start_date`` on every transactions request.

    When a value is given (the last sync time), it is moved back by
    ``_SYNC_OVERLAP`` so transactions that settle after their timestamp (e.g.
    card spend that was pending on the previous run) are still picked up.
    Re-fetched rows are deduplicated by the ``(source, source_tx_id)`` constraint.
    """
    if value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt -= _SYNC_OVERLAP
    else:
        dt = datetime.now(timezone.utc) - timedelta(days=settings.ASPIRE_SYNC_LOOKBACK_DAYS)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_tx_date(value: str) -> date:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_LOCAL_TZ).date()


def _next_page(metadata: dict[str, Any], requested_page: int) -> str | None:
    """Return the next page number as a cursor string, or None when done.

    Guards against a next page that does not advance past the requested one,
    which would otherwise loop the sync orchestrator forever.
    """
    next_url = metadata.get("next_page_url")
    if not next_url:
        return None
    page = parse_qs(urlparse(next_url).query).get("page")
    try:
        if page:
            next_page = int(page[0])
        elif metadata.get("current_page") is not None:
            next_page = int(metadata["current_page"]) + 1
        else:
            return None
    except (TypeError, ValueError):
        return None
    return str(next_page) if next_page > requested_page else None


def _is_operating_account(item: dict[str, Any]) -> bool:
    """Active debit accounts are the bank accounts; ``advance`` is a credit line."""
    return item.get("account_type") == "debit" and item.get("account_status") in (None, "active")


class AspireProvider(
    IntegrationProvider,
    TransactionSyncProvider,
    BalanceSyncProvider,
):
    """Aspire business account integration (read-only: transactions + balances)."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._debit_account_ids: set[str] | None = None
        self._debit_accounts_fetched_at: float = 0.0

    @property
    def name(self) -> str:
        return "aspire"

    @property
    def display_name(self) -> str:
        return "Aspire"

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.ASPIRE_CLIENT_ID and settings.ASPIRE_API_KEY)

    # --- Auth ---

    def _token_valid(self) -> bool:
        return self._token is not None and time.time() < self._token_expires_at - 60

    async def _get_token(self) -> str:
        if not self._token_valid():
            # Scheduler jobs share this singleton; avoid concurrent logins.
            async with self._token_lock:
                if not self._token_valid():
                    await self._refresh_token()
        if self._token is None:
            raise ProviderAPIError(self.name, 0, "Authentication did not return an access token")
        return self._token

    async def _refresh_token(self) -> None:
        if not self.is_configured():
            raise ProviderAPIError(
                self.name,
                0,
                "ASPIRE_CLIENT_ID and ASPIRE_API_KEY must be configured",
            )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.ASPIRE_BASE_URL}/login",
                headers={"Content-Type": "application/json"},
                json={
                    "grant_type": "client_credentials",
                    "client_id": settings.ASPIRE_CLIENT_ID,
                    "client_secret": settings.ASPIRE_API_KEY,
                },
            )
        if resp.status_code == 429:
            raise ProviderRateLimitError(self.name, 429, "Rate limited on login", retry_after=60)
        if resp.status_code not in (200, 201):
            raise ProviderAPIError(self.name, resp.status_code, resp.text)
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ProviderAPIError(self.name, resp.status_code, "Login response missing access_token")
        self._token = token
        self._token_expires_at = time.time() + int(data.get("expires_in", 900))

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request; refresh the token and retry once on 401."""
        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/json"

        async def _send(token: str) -> httpx.Response:
            headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(timeout=30) as client:
                return await client.request(
                    method,
                    f"{settings.ASPIRE_BASE_URL}{path}",
                    headers=headers,
                    **kwargs,
                )

        token = await self._get_token()
        resp = await _send(token)
        if resp.status_code == 401:
            async with self._token_lock:
                # Another caller may already have refreshed the token.
                if self._token == token:
                    self._token = None
                    await self._refresh_token()
            resp = await _send(await self._get_token())

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
        except (ProviderAPIError, httpx.HTTPError) as e:
            return {"status": "error", "provider": self.name, "error": str(e)}

    async def _get_debit_account_ids(self, refresh: bool = False) -> set[str]:
        """IDs of active operating accounts, cached for ``_ACCOUNTS_CACHE_TTL``."""
        stale = time.time() - self._debit_accounts_fetched_at > _ACCOUNTS_CACHE_TTL
        if refresh or stale or self._debit_account_ids is None:
            data = await self._request("GET", "/accounts")
            self._debit_account_ids = {
                str(item["id"]) for item in data.get("data", []) or [] if item.get("id") and _is_operating_account(item)
            }
            self._debit_accounts_fetched_at = time.time()
        return self._debit_account_ids

    # --- TransactionSyncProvider ---

    async def sync_transactions(
        self,
        since: str | None = None,
        cursor: str | None = None,
    ) -> tuple[list[SyncedTransaction], str | None]:
        if since is None and cursor:
            # The first-sync window (now - lookback) moves between runs, so a
            # saved page number no longer points at the same rows. Restart
            # from page 1; already-imported rows are deduplicated.
            cursor = None

        # Refresh the account list at the start of each run (no cursor).
        debit_ids = await self._get_debit_account_ids(refresh=cursor is None)

        requested_page = int(cursor) if cursor else 1
        params: dict[str, Any] = {"start_date": _to_aspire_timestamp(since)}
        if cursor:
            params["page"] = cursor

        data = await self._request("GET", "/transactions", params=params)
        items = data.get("data", []) or []
        next_cursor = _next_page(data.get("metadata", {}) or {}, requested_page)

        transactions: list[SyncedTransaction] = []
        for item in items:
            if (item.get("status") or "").lower() in _SKIP_STATUSES:
                continue
            tx_id = item.get("id")
            if not tx_id:
                continue
            # Skip credit-line (advance) and inactive accounts: they share the
            # currency of the operating account but are not the bank account.
            account_id = item.get("account_id")
            if account_id and str(account_id) not in debit_ids:
                continue
            try:
                tx_date = _parse_tx_date(item.get("datetime") or "")
            except ValueError:
                logger.warning("Skipping Aspire transaction %s: bad datetime %r", tx_id, item.get("datetime"))
                continue

            currency = (item.get("currency_code") or "SGD").upper()
            amount = from_minor_units(item.get("amount"), currency)
            # Aspire signs debits negatively; enforce it in case a row comes back unsigned.
            if (item.get("type") or "").lower() == "debit":
                amount = -abs(amount)

            counterparty = item.get("counterparty_name")
            if counterparty in ("", "N/A"):
                counterparty = None

            transactions.append(
                SyncedTransaction(
                    source_tx_id=tx_id,
                    tx_date=tx_date,
                    amount=amount,
                    currency=currency,
                    counterparty=counterparty,
                    reference=item.get("reference") or None,
                    description=item.get("ref_code") or item.get("channel"),
                    raw_data=item,
                )
            )

        return transactions, next_cursor

    # --- BalanceSyncProvider ---

    async def sync_balances(self) -> list[BalanceInfo]:
        data = await self._request("GET", "/accounts")
        now = datetime.now(timezone.utc)
        # Aspire can hold several accounts per currency (e.g. a DBS SWIFT account and a
        # Currency Cloud local account for USD). The ledger has one account per currency
        # and transaction sync already merges them by currency, so sum balances to match.
        totals: dict[str, Decimal] = {}
        for item in data.get("data", []) or []:
            # Only operating (debit) accounts map to bank accounts in the ledger.
            if not _is_operating_account(item):
                continue
            currency = (item.get("currency_code") or "SGD").upper()
            amount = from_minor_units(item.get("available_balance"), currency)
            totals[currency] = totals.get(currency, Decimal("0")) + amount
        return [
            BalanceInfo(currency=currency, available_balance=total, pending_balance=None, as_of=now)
            for currency, total in totals.items()
        ]


register_provider(AspireProvider())
