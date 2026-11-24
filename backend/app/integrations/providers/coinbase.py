"""Coinbase (Coinbase App API v2) integration provider — read-only.

Docs: https://docs.cdp.coinbase.com/coinbase-app/track-apis/transactions

- Auth: CDP Secret API key, Ed25519 (EdDSA, the CDP default) or ECDSA (ES256).
  Every request carries a fresh JWT (2-minute lifetime) whose ``uri`` claim is
  ``"{METHOD} api.coinbase.com{path}"``.
- Accounts: ``GET /v2/accounts`` (one account per currency: USDC, USDT, SGD, ...).
- Transactions: ``GET /v2/accounts/{id}/transactions``, newest first, paginated
  through ``pagination.next_uri``. ``amount`` is signed in the account's currency
  (negative = money out); ``network.hash`` carries the on-chain hash for sends.

Synced rows land in ``BankTransaction`` with ``source="coinbase"`` and are routed to
backoffice accounts with ``statement_source="coinbase"`` by currency (one backoffice
account per Coinbase currency, e.g. "Coinbase USDT", "Coinbase SGD").
"""

import base64
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from jose import jwt

from app.config import settings
from app.integrations import register_provider
from app.integrations.base import BalanceSyncProvider, IntegrationProvider, TransactionSyncProvider
from app.integrations.capabilities import BalanceInfo, SyncedTransaction
from app.integrations.exceptions import ProviderAPIError, ProviderRateLimitError

logger = logging.getLogger(__name__)

_HOST = "api.coinbase.com"
_LOCAL_TZ = ZoneInfo("Asia/Singapore")
# Re-read this much history before the last sync so late-completing rows are caught;
# duplicates are dropped by the (source, source_tx_id) unique constraint.
_SYNC_OVERLAP = timedelta(days=7)
_MAX_PAGES_PER_ACCOUNT = 200
# Only rows that actually moved money. Pending rows are picked up once completed.
_BOOKED_STATUSES = {"completed"}


def _private_key() -> str:
    """The PEM key from settings; ``\\n`` escapes (single-line .env values) become newlines."""
    key = (settings.COINBASE_API_PRIVATE_KEY or "").strip().strip('"').strip("'")
    return key.replace("\\n", "\n")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _ed25519_key(secret: str):
    """CDP Ed25519 secret: base64 of 64 bytes (32-byte seed + 32-byte public key) or of the 32-byte seed."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw = base64.b64decode(secret.strip())
    if len(raw) not in (32, 64):
        raise ValueError("Ed25519 secret must decode to 32 or 64 bytes")
    return Ed25519PrivateKey.from_private_bytes(raw[:32])


def key_algorithm() -> str:
    """ES256 for an EC PEM key, EdDSA for a CDP Ed25519 secret."""
    return "ES256" if "BEGIN" in _private_key() else "EdDSA"


def build_jwt(method: str, path: str, now: float | None = None) -> str:
    """JWT for one request; ``path`` must exclude the query string."""
    issued = int(now if now is not None else time.time())
    claims = {
        "sub": settings.COINBASE_API_KEY_NAME,
        "iss": "cdp",
        "nbf": issued,
        "exp": issued + 120,
        "uri": f"{method.upper()} {_HOST}{path}",
    }
    headers = {"kid": settings.COINBASE_API_KEY_NAME, "nonce": secrets.token_hex(16), "typ": "JWT"}
    algorithm = key_algorithm()
    if algorithm == "ES256":
        return jwt.encode(claims, _private_key(), algorithm="ES256", headers=headers)

    # EdDSA (python-jose has no Ed25519 support): sign the compact JWS by hand.
    header = {"alg": "EdDSA", **headers}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    signature = _ed25519_key(_private_key()).sign(signing_input.encode())
    return signing_input + "." + _b64url(signature)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def map_transaction(item: dict[str, Any]) -> SyncedTransaction | None:
    """Coinbase transaction → SyncedTransaction (None for rows that did not book)."""
    if (item.get("status") or "").lower() not in _BOOKED_STATUSES:
        return None
    created = _parse_dt(item.get("created_at"))
    money = item.get("amount") or {}
    if not item.get("id") or created is None or money.get("amount") is None:
        return None

    tx_type = item.get("type") or "tx"
    network = item.get("network") or {}
    details = item.get("details") or {}
    counterparty_obj = (item.get("to") if Decimal(str(money["amount"])) < 0 else item.get("from")) or {}
    counterparty = (
        counterparty_obj.get("address")
        or counterparty_obj.get("email")
        or counterparty_obj.get("name")
        or details.get("subtitle")
    )
    native = item.get("native_amount") or {}
    description_bits = [tx_type, details.get("title") or item.get("description")]
    if native.get("amount") is not None:
        description_bits.append(f"({native.get('currency')} {native.get('amount')})")

    return SyncedTransaction(
        source_tx_id=str(item["id"]),
        tx_date=created.astimezone(_LOCAL_TZ).date(),
        amount=Decimal(str(money["amount"])),
        currency=str(money.get("currency") or "").upper(),
        counterparty=counterparty or None,
        reference=network.get("hash") or None,
        description=" ".join(str(b) for b in description_bits if b),
        raw_data=item,
    )


class CoinbaseProvider(IntegrationProvider, TransactionSyncProvider, BalanceSyncProvider):
    """Coinbase App account (custodial) — transactions and balances, read-only."""

    @property
    def name(self) -> str:
        return "coinbase"

    @property
    def display_name(self) -> str:
        return "Coinbase"

    @staticmethod
    def is_configured() -> bool:
        return bool(settings.COINBASE_API_KEY_NAME and settings.COINBASE_API_PRIVATE_KEY)

    async def _get(self, path_and_query: str) -> Any:
        if not self.is_configured():
            raise ProviderAPIError(self.name, 0, "COINBASE_API_KEY_NAME and COINBASE_API_PRIVATE_KEY must be configured")
        path = urlsplit(path_and_query).path
        try:
            token = build_jwt("GET", path)
        except Exception as exc:  # malformed PEM etc. — never echo the key
            raise ProviderAPIError(self.name, 0, f"Cannot sign request with COINBASE_API_PRIVATE_KEY: {type(exc).__name__}") from exc
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            resp = await client.get(
                f"https://{_HOST}{path_and_query}",
                headers={"Authorization": f"Bearer {token}", "CB-VERSION": "2024-01-01"},
            )
        if resp.status_code == 429:
            raise ProviderRateLimitError(self.name, 429, "Rate limited", retry_after=int(resp.headers.get("Retry-After", "60")))
        if resp.status_code >= 400:
            raise ProviderAPIError(self.name, resp.status_code, resp.text[:500])
        return resp.json()

    async def _paginate(self, path_and_query: str, max_pages: int = _MAX_PAGES_PER_ACCOUNT, stop_before: datetime | None = None):
        """Yield items across pages (newest first); stop once items are older than ``stop_before``."""
        next_uri: str | None = path_and_query
        pages = 0
        while next_uri and pages < max_pages:
            body = await self._get(next_uri)
            pages += 1
            items = body.get("data") or []
            for item in items:
                yield item
            if stop_before is not None and items:
                oldest = _parse_dt(items[-1].get("created_at"))
                if oldest is not None and oldest < stop_before:
                    return
            next_uri = (body.get("pagination") or {}).get("next_uri")

    async def list_accounts(self) -> list[dict[str, Any]]:
        return [a async for a in self._paginate("/v2/accounts?limit=100")]

    async def test_connection(self) -> dict[str, Any]:
        try:
            accounts = await self.list_accounts()
            return {"status": "ok", "provider": self.name, "accounts": len(accounts)}
        except (ProviderAPIError, httpx.HTTPError) as e:
            return {"status": "error", "provider": self.name, "error": str(e)}

    # --- TransactionSyncProvider ---

    async def sync_transactions(
        self,
        since: str | None = None,
        cursor: str | None = None,
    ) -> tuple[list[SyncedTransaction], str | None]:
        """All booked transactions across Coinbase accounts since ``since`` (minus overlap).

        Returns everything in one batch (no cursor): Coinbase pages per account, and the
        volume for a company account is small.
        """
        stop_before = None
        if since:
            stop_before = _parse_dt(since)
            if stop_before is not None:
                stop_before -= _SYNC_OVERLAP

        out: list[SyncedTransaction] = []
        for account in await self.list_accounts():
            if not account.get("id"):
                continue
            async for item in self._paginate(f"/v2/accounts/{account['id']}/transactions?limit=100", stop_before=stop_before):
                created = _parse_dt(item.get("created_at"))
                if stop_before is not None and created is not None and created < stop_before:
                    continue
                tx = map_transaction(item)
                if tx is not None:
                    out.append(tx)
        return out, None

    # --- BalanceSyncProvider ---

    async def sync_balances(self) -> list[BalanceInfo]:
        totals: dict[str, Decimal] = {}
        for account in await self.list_accounts():
            balance = account.get("balance") or {}
            currency = str(balance.get("currency") or (account.get("currency") or {}).get("code") or "").upper()
            if not currency or balance.get("amount") is None:
                continue
            totals[currency] = totals.get(currency, Decimal("0")) + Decimal(str(balance["amount"]))
        now = datetime.now(timezone.utc)
        return [BalanceInfo(currency=c, available_balance=v, pending_balance=None, as_of=now) for c, v in totals.items()]


register_provider(CoinbaseProvider())
