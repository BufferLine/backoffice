"""Unit tests for the Aspire integration provider."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings
from app.integrations import get_provider
from app.integrations.base import BalanceSyncProvider, TransactionSyncProvider
from app.integrations.capabilities import Capability
from app.integrations.exceptions import ProviderAPIError, ProviderRateLimitError
from app.integrations.providers import aspire as aspire_mod
from app.integrations.providers.aspire import AspireProvider, from_minor_units

_RealAsyncClient = httpx.AsyncClient


def _tx(**overrides) -> dict:
    base = {
        "id": "9c2a8d10-0fdd-4dc9-8a4c-5eb123e456aa",
        "account_id": "9b8ad7de-4f4d-4a9a-8bbc-5eb123e456aa",
        "ref_code": "CACPLWGPNC6W",
        "datetime": "2026-10-30T10:41:32Z",
        "type": "credit",
        "is_fx_transfer": False,
        "channel": "banktransfer",
        "status": "settled",
        "currency_code": "SGD",
        "amount": 135000,
        "reference": "INV-2026-001",
        "counterparty_name": "Sample Company",
        "counterparty_id": "N/A",
        "balance": 825000,
    }
    base.update(overrides)
    return base


def _page(items: list[dict], next_page_url: str | None = None, current_page: int = 1) -> dict:
    return {
        "data": items,
        "metadata": {
            "total": len(items),
            "per_page": 100,
            "current_page": current_page,
            "next_page_url": next_page_url,
            "prev_page_url": None,
        },
    }


DEBIT_ACCOUNT = "9b8ad7de-4f4d-4a9a-8bbc-5eb123e456aa"
ADVANCE_ACCOUNT = "92eaa6c8-2814-4d37-bfc2-0b000b123456"

_ACCOUNTS = {
    "data": [
        {"id": DEBIT_ACCOUNT, "account_status": "active", "account_type": "debit",
         "available_balance": 188900, "currency_code": "SGD"},
        {"id": ADVANCE_ACCOUNT, "account_status": "active", "account_type": "advance",
         "available_balance": 11784, "currency_code": "SGD"},
    ]
}


def _fake_api(*tx_pages: dict, accounts: dict | None = None) -> AsyncMock:
    """AsyncMock for ``_request`` that serves /accounts and successive /transactions pages."""
    pages = iter(tx_pages)

    async def handler(method, path, **kwargs):
        if path == "/accounts":
            return accounts or _ACCOUNTS
        return next(pages)

    return AsyncMock(side_effect=handler)


def _tx_calls(mock: AsyncMock) -> list:
    return [c for c in mock.call_args_list if c.args[1] == "/transactions"]


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "ASPIRE_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "ASPIRE_API_KEY", "test-secret")
    monkeypatch.setattr(settings, "ASPIRE_BASE_URL", "https://aspire.test/public/v1")


def _mock_http(handler):
    """Route the provider's httpx.AsyncClient through a MockTransport."""
    transport = httpx.MockTransport(handler)
    return patch.object(
        aspire_mod.httpx,
        "AsyncClient",
        lambda **kw: _RealAsyncClient(transport=transport, **kw),
    )


class TestMinorUnits:
    def test_two_decimal_currency(self):
        assert from_minor_units(135000, "SGD") == Decimal("1350.00")

    def test_negative_amount(self):
        assert from_minor_units(-1050, "USD") == Decimal("-10.50")

    def test_zero_decimal_currency(self):
        assert from_minor_units(-10000, "IDR") == Decimal("-10000")
        assert from_minor_units(500, "jpy") == Decimal("500")

    def test_three_decimal_currency(self):
        assert from_minor_units(1234, "KWD") == Decimal("1.234")

    def test_none_is_zero(self):
        assert from_minor_units(None, "SGD") == Decimal("0")


class TestCapabilities:
    def test_registered(self):
        assert isinstance(get_provider("aspire"), AspireProvider)

    def test_capabilities(self):
        p = AspireProvider()
        assert isinstance(p, TransactionSyncProvider)
        assert isinstance(p, BalanceSyncProvider)
        assert set(p.capabilities) == {Capability.SYNC_TRANSACTIONS, Capability.SYNC_BALANCE}

    def test_is_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "ASPIRE_CLIENT_ID", None)
        monkeypatch.setattr(settings, "ASPIRE_API_KEY", None)
        assert AspireProvider.is_configured() is False
        monkeypatch.setattr(settings, "ASPIRE_CLIENT_ID", "id")
        monkeypatch.setattr(settings, "ASPIRE_API_KEY", "secret")
        assert AspireProvider.is_configured() is True


class TestSyncTransactions:
    @pytest.mark.asyncio
    async def test_maps_fields(self):
        p = AspireProvider()
        debit = _tx(
            id="debit-1",
            type="debit",
            amount=-2500,
            counterparty_name="N/A",
            reference="",
            datetime="2026-10-30T17:30:00Z",  # 01:30 on 31 Oct in Singapore
        )
        mock = _fake_api(_page([_tx(), debit]))
        with patch.object(p, "_request", mock):
            txs, cursor = await p.sync_transactions(since="2026-10-29T00:00:00+00:00")

        assert cursor is None
        assert len(txs) == 2

        credit = txs[0]
        assert credit.source_tx_id == "9c2a8d10-0fdd-4dc9-8a4c-5eb123e456aa"
        assert credit.amount == Decimal("1350.00")
        assert credit.currency == "SGD"
        assert credit.tx_date == date(2026, 10, 30)
        assert credit.counterparty == "Sample Company"
        assert credit.reference == "INV-2026-001"
        assert credit.description == "CACPLWGPNC6W"
        assert credit.raw_data["balance"] == 825000

        d = txs[1]
        assert d.amount == Decimal("-25.00")
        assert d.tx_date == date(2026, 10, 31)  # converted to Singapore local date
        assert d.counterparty is None
        assert d.reference is None

    @pytest.mark.asyncio
    async def test_unsigned_debit_is_made_negative(self):
        p = AspireProvider()
        mock = _fake_api(_page([_tx(type="debit", amount=2500)]))
        with patch.object(p, "_request", mock):
            txs, _ = await p.sync_transactions(since="2026-10-29T00:00:00Z")
        assert txs[0].amount == Decimal("-25.00")

    @pytest.mark.asyncio
    async def test_skips_pending_and_invalid_rows(self):
        p = AspireProvider()
        rows = [
            _tx(id="pending", status="pending", channel="card"),
            _tx(id=None),
            _tx(id="bad-date", datetime="not-a-date"),
            _tx(id="ok"),
        ]
        with patch.object(p, "_request", _fake_api(_page(rows))):
            txs, _ = await p.sync_transactions(since="2026-10-29T00:00:00Z")
        assert [t.source_tx_id for t in txs] == ["ok"]

    @pytest.mark.asyncio
    async def test_since_is_normalised_with_overlap(self):
        p = AspireProvider()
        mock = _fake_api(_page([]))
        with patch.object(p, "_request", mock):
            await p.sync_transactions(since="2026-11-05T03:15:42.123456+00:00", cursor="3")

        (call,) = _tx_calls(mock)
        assert call.kwargs["params"] == {"start_date": "2026-10-29T03:15:42Z", "page": "3"}

    @pytest.mark.asyncio
    async def test_default_start_date_when_never_synced(self):
        p = AspireProvider()
        mock = _fake_api(_page([]))
        with patch.object(p, "_request", mock):
            await p.sync_transactions()

        params = _tx_calls(mock)[0].kwargs["params"]
        assert "page" not in params
        start = datetime.strptime(params["start_date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        expected = datetime.now(timezone.utc) - timedelta(days=settings.ASPIRE_SYNC_LOOKBACK_DAYS)
        assert abs((start - expected).total_seconds()) < 60

    @pytest.mark.asyncio
    async def test_next_page_cursor_from_url(self):
        p = AspireProvider()
        page = _page(
            [_tx()],
            next_page_url="https://api.aspireapp.com/public/v1/transactions?start_date=2026-10-01T00%3A00%3A00Z&page=2",
        )
        with patch.object(p, "_request", _fake_api(page)):
            _, cursor = await p.sync_transactions(since="2026-10-01T00:00:00Z")
        assert cursor == "2"

    @pytest.mark.asyncio
    async def test_next_page_cursor_falls_back_to_current_page(self):
        p = AspireProvider()
        page = _page([_tx()], next_page_url="https://api.aspireapp.com/public/v1/transactions", current_page=4)
        with patch.object(p, "_request", _fake_api(page)):
            _, cursor = await p.sync_transactions(since="2026-10-01T00:00:00Z", cursor="4")
        assert cursor == "5"


    @pytest.mark.asyncio
    async def test_first_sync_resume_restarts_from_page_one(self):
        p = AspireProvider()
        mock = _fake_api(_page([]))
        with patch.object(p, "_request", mock):
            await p.sync_transactions(since=None, cursor="6")
        assert "page" not in _tx_calls(mock)[0].kwargs["params"]

    @pytest.mark.asyncio
    async def test_skips_advance_and_unknown_accounts(self):
        p = AspireProvider()
        rows = [
            _tx(id="op", account_id=DEBIT_ACCOUNT),
            _tx(id="credit-line", account_id=ADVANCE_ACCOUNT, type="debit", amount=-5000),
            _tx(id="unknown", account_id="00000000-0000-0000-0000-000000000000"),
        ]
        with patch.object(p, "_request", _fake_api(_page(rows))):
            txs, _ = await p.sync_transactions(since="2026-10-29T00:00:00Z")
        assert [t.source_tx_id for t in txs] == ["op"]

    @pytest.mark.asyncio
    async def test_non_advancing_next_page_stops(self):
        p = AspireProvider()
        page = _page(
            [_tx()],
            next_page_url="https://api.aspireapp.com/public/v1/transactions?page=2",
            current_page=2,
        )
        with patch.object(p, "_request", _fake_api(page)):
            _, cursor = await p.sync_transactions(since="2026-10-01T00:00:00Z", cursor="2")
        assert cursor is None

    @pytest.mark.asyncio
    async def test_multi_page_run_reuses_account_cache(self):
        p = AspireProvider()
        page1 = _page(
            [_tx(id="a")],
            next_page_url="https://api.aspireapp.com/public/v1/transactions?page=2",
        )
        page2 = _page([_tx(id="b")], current_page=2)
        mock = _fake_api(page1, page2)
        seen: list[str] = []
        cursor = None
        with patch.object(p, "_request", mock):
            while True:
                txs, cursor = await p.sync_transactions(since="2026-10-01T00:00:00Z", cursor=cursor)
                seen += [t.source_tx_id for t in txs]
                if cursor is None:
                    break
        assert seen == ["a", "b"]
        paths = [c.args[1] for c in mock.call_args_list]
        assert paths == ["/accounts", "/transactions", "/transactions"]


class TestSyncBalances:
    @pytest.mark.asyncio
    async def test_only_active_debit_accounts(self):
        p = AspireProvider()
        data = {
            "data": [
                {"id": "a1", "account_status": "active", "account_type": "debit",
                 "available_balance": 188900, "currency_code": "SGD"},
                {"id": "a2", "account_status": "inactive", "account_type": "advance",
                 "available_balance": 11784, "currency_code": "SGD"},
                {"id": "a3", "account_status": "active", "account_type": "debit",
                 "available_balance": 27449, "currency_code": "USD"},
                {"id": "a4", "account_status": "inactive", "account_type": "debit",
                 "available_balance": 100, "currency_code": "EUR"},
            ]
        }
        mock = AsyncMock(return_value=data)
        with patch.object(p, "_request", mock):
            balances = await p.sync_balances()

        mock.assert_called_once_with("GET", "/accounts")
        assert [(b.currency, b.available_balance) for b in balances] == [
            ("SGD", Decimal("1889.00")),
            ("USD", Decimal("274.49")),
        ]
        assert all(b.pending_balance is None and b.as_of is not None for b in balances)

    @pytest.mark.asyncio
    async def test_sums_multiple_accounts_per_currency(self):
        p = AspireProvider()
        data = {
            "data": [
                {"id": "sgd", "account_status": "active", "account_type": "debit",
                 "available_balance": 2909458, "currency_code": "SGD"},
                {"id": "usd-dbs", "account_status": "active", "account_type": "debit",
                 "available_balance": 10000, "currency_code": "USD"},
                {"id": "usd-ccy-cloud", "account_status": "active", "account_type": "debit",
                 "available_balance": 2550, "currency_code": "USD"},
            ]
        }
        with patch.object(p, "_request", AsyncMock(return_value=data)):
            balances = await p.sync_balances()
        assert [(b.currency, b.available_balance) for b in balances] == [
            ("SGD", Decimal("29094.58")),
            ("USD", Decimal("125.50")),
        ]


class TestHTTP:
    @pytest.mark.asyncio
    async def test_login_and_bearer_token(self, configured):
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if request.url.path == "/public/v1/login":
                return httpx.Response(200, json={"access_token": "tok-1", "token_type": "Bearer", "expires_in": 900})
            if request.url.path == "/public/v1/accounts":
                return httpx.Response(200, json=_ACCOUNTS)
            return httpx.Response(200, json=_page([_tx()]))

        p = AspireProvider()
        with _mock_http(handler):
            txs, _ = await p.sync_transactions(since="2026-10-29T00:00:00Z")
            await p.sync_transactions(since="2026-10-29T00:00:00Z")

        assert len(txs) == 1
        calls = [c for c in calls if not c.url.path.endswith("/accounts")]
        login, first, second = calls
        assert login.method == "POST"
        assert json.loads(login.content) == {
            "grant_type": "client_credentials",
            "client_id": "test-client",
            "client_secret": "test-secret",
        }
        assert first.headers["Authorization"] == "Bearer tok-1"
        assert first.url.params["start_date"] == "2026-10-22T00:00:00Z"
        # Token is cached: no second login.
        assert second.headers["Authorization"] == "Bearer tok-1"

    @pytest.mark.asyncio
    async def test_retries_once_on_401(self, configured):
        tokens = iter(["stale", "fresh"])
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/login"):
                return httpx.Response(200, json={"access_token": next(tokens), "expires_in": 900})
            seen.append(request.headers["Authorization"])
            if request.headers["Authorization"] == "Bearer stale":
                return httpx.Response(401, json={"error": {"code": "unauthorized"}})
            return httpx.Response(200, json={"data": []})

        p = AspireProvider()
        with _mock_http(handler):
            assert await p.sync_balances() == []
        assert seen == ["Bearer stale", "Bearer fresh"]

    @pytest.mark.asyncio
    async def test_rate_limit(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/login"):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 900})
            return httpx.Response(429, headers={"Retry-After": "12"}, json={"error": {"code": "too_many_requests"}})

        p = AspireProvider()
        with _mock_http(handler), pytest.raises(ProviderRateLimitError) as exc:
            await p.sync_balances()
        assert exc.value.retry_after == 12

    @pytest.mark.asyncio
    async def test_api_error(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/login"):
                return httpx.Response(200, json={"access_token": "t", "expires_in": 900})
            if request.url.path.endswith("/accounts"):
                return httpx.Response(200, json=_ACCOUNTS)
            return httpx.Response(422, json={"error": {"code": "invalid_data"}})

        p = AspireProvider()
        with _mock_http(handler), pytest.raises(ProviderAPIError) as exc:
            await p.sync_transactions(since="2026-10-29T00:00:00Z")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_test_connection_reports_login_failure(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"code": "invalid_client"}})

        p = AspireProvider()
        with _mock_http(handler):
            result = await p.test_connection()
        assert result["status"] == "error"
        assert "400" in result["error"]

    @pytest.mark.asyncio
    async def test_refreshes_token_near_expiry(self, configured):
        tokens = iter(["old", "new"])
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/login"):
                return httpx.Response(200, json={"access_token": next(tokens), "expires_in": 900})
            seen.append(request.headers["Authorization"])
            return httpx.Response(200, json={"data": []})

        p = AspireProvider()
        with _mock_http(handler):
            await p.sync_balances()
            p._token_expires_at = time.time() + 30  # inside the 60s refresh margin
            await p.sync_balances()
        assert seen == ["Bearer old", "Bearer new"]

    @pytest.mark.asyncio
    async def test_test_connection_reports_transport_error(self, configured):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        p = AspireProvider()
        with _mock_http(handler):
            result = await p.test_connection()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "ASPIRE_CLIENT_ID", None)
        monkeypatch.setattr(settings, "ASPIRE_API_KEY", None)
        p = AspireProvider()
        with pytest.raises(ProviderAPIError, match="ASPIRE_CLIENT_ID"):
            await p.sync_balances()
