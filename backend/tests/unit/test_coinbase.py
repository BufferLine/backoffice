"""Unit tests for the Coinbase (Coinbase App API v2) provider — no network."""

import base64
import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jose import jwt as jose_jwt

from app.config import settings
from app.integrations import get_provider
from app.integrations.capabilities import Capability
from app.integrations.providers import coinbase as cb
from app.integrations.providers.coinbase import CoinbaseProvider, build_jwt, key_algorithm, map_transaction

KEY_NAME = "organizations/org-1/apiKeys/key-1"


def _pad(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.fixture
def ed_key(monkeypatch):
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(settings, "COINBASE_API_KEY_NAME", KEY_NAME)
    monkeypatch.setattr(settings, "COINBASE_API_PRIVATE_KEY", base64.b64encode(seed + pub).decode())
    return key


@pytest.fixture
def ec_key(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
    ).decode()
    monkeypatch.setattr(settings, "COINBASE_API_KEY_NAME", KEY_NAME)
    monkeypatch.setattr(settings, "COINBASE_API_PRIVATE_KEY", pem.replace("\n", "\\n"))  # single-line .env form
    return key


class TestJWT:
    def test_eddsa_for_cdp_ed25519_secret(self, ed_key):
        assert key_algorithm() == "EdDSA"
        token = build_jwt("get", "/v2/accounts", now=1_800_000_000)
        header_b64, claims_b64, sig_b64 = token.split(".")
        ed_key.public_key().verify(_pad(sig_b64), f"{header_b64}.{claims_b64}".encode())  # raises if invalid
        header, claims = json.loads(_pad(header_b64)), json.loads(_pad(claims_b64))
        assert header["alg"] == "EdDSA" and header["kid"] == KEY_NAME and len(header["nonce"]) == 32
        assert claims == {
            "sub": KEY_NAME, "iss": "cdp", "nbf": 1_800_000_000, "exp": 1_800_000_120,
            "uri": "GET api.coinbase.com/v2/accounts",
        }

    def test_es256_for_ec_pem(self, ec_key):
        assert key_algorithm() == "ES256"
        token = build_jwt("GET", "/v2/accounts/abc/transactions", now=1_800_000_000)
        pub = ec_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        claims = jose_jwt.decode(token, pub, algorithms=["ES256"], options={"verify_nbf": False, "verify_exp": False})
        assert claims["uri"] == "GET api.coinbase.com/v2/accounts/abc/transactions"
        assert jose_jwt.get_unverified_header(token)["kid"] == KEY_NAME

    def test_fresh_nonce_per_request(self, ed_key):
        a, b = build_jwt("GET", "/v2/accounts"), build_jwt("GET", "/v2/accounts")
        assert json.loads(_pad(a.split(".")[0]))["nonce"] != json.loads(_pad(b.split(".")[0]))["nonce"]


class TestMapping:
    def _tx(self, **over):
        base = {
            "id": "tx-1", "type": "send", "status": "completed",
            "amount": {"amount": "18650.000000", "currency": "USDT"},
            "native_amount": {"amount": "23824.63", "currency": "SGD"},
            "created_at": "2026-10-19T17:30:14Z",  # 20 Oct 01:30 in Singapore
            "network": {"status": "confirmed", "hash": "0xdeca31"},
            "from": {"address": "0x6f12"},
            "details": {"title": "Received USDT"},
        }
        base.update(over)
        return base

    def test_crypto_deposit(self):
        tx = map_transaction(self._tx())
        assert tx.source_tx_id == "tx-1"
        assert tx.amount == Decimal("18650.000000") and tx.currency == "USDT"
        assert tx.tx_date == date(2026, 10, 20)
        assert tx.reference == "0xdeca31"
        assert tx.counterparty == "0x6f12"
        assert tx.description == "send Received USDT (SGD 23824.63)"

    def test_trade_fill_is_signed(self):
        tx = map_transaction(self._tx(
            type="advanced_trade_fill", amount={"amount": "-6050.4", "currency": "USDC"}, network=None, details={},
            advanced_trade_fill={"product_id": "USDC-SGD", "order_side": "SELL", "fill_price": "1.277"},
        ))
        assert tx.amount == Decimal("-6050.4") and tx.reference is None

    @pytest.mark.parametrize("status", ["pending", "failed", "canceled", "waiting_for_clearing"])
    def test_unbooked_statuses_are_skipped(self, status):
        assert map_transaction(self._tx(status=status)) is None

    def test_malformed_rows_are_skipped(self):
        assert map_transaction(self._tx(id=None)) is None
        assert map_transaction(self._tx(created_at="nope")) is None
        assert map_transaction(self._tx(amount={})) is None


class TestProvider:
    def test_registered_and_capabilities(self):
        p = get_provider("coinbase")
        assert isinstance(p, CoinbaseProvider)
        assert set(p.capabilities) == {Capability.SYNC_TRANSACTIONS, Capability.SYNC_BALANCE}

    @pytest.mark.asyncio
    async def test_unconfigured(self, monkeypatch):
        monkeypatch.setattr(settings, "COINBASE_API_KEY_NAME", None)
        monkeypatch.setattr(settings, "COINBASE_API_PRIVATE_KEY", None)
        result = await CoinbaseProvider().test_connection()
        assert result["status"] == "error" and "COINBASE_API_KEY_NAME" in result["error"]

    @pytest.mark.asyncio
    async def test_bad_key_never_echoed(self, monkeypatch):
        monkeypatch.setattr(settings, "COINBASE_API_KEY_NAME", KEY_NAME)
        monkeypatch.setattr(settings, "COINBASE_API_PRIVATE_KEY", "c2VjcmV0LWJ1dC1ub3QtYS1rZXk=")
        result = await CoinbaseProvider().test_connection()
        assert result["status"] == "error"
        assert "c2VjcmV0" not in result["error"]

    @pytest.mark.asyncio
    async def test_sync_balances_sums_per_currency(self):
        p = CoinbaseProvider()
        accounts = [
            {"id": "a", "balance": {"amount": "4.277536", "currency": "USDC"}},
            {"id": "b", "balance": {"amount": "0.01", "currency": "USDT"}},
            {"id": "c", "balance": {"amount": "1.00", "currency": "USDC"}},
            {"id": "d", "currency": {"code": "SGD"}, "balance": {"amount": "0.00"}},
        ]
        with patch.object(p, "list_accounts", AsyncMock(return_value=accounts)):
            balances = await p.sync_balances()
        assert {(b.currency, b.available_balance) for b in balances} == {
            ("USDC", Decimal("5.277536")), ("USDT", Decimal("0.01")), ("SGD", Decimal("0.00")),
        }

    @pytest.mark.asyncio
    async def test_sync_transactions_pages_and_stops_at_since(self):
        p = CoinbaseProvider()
        pages = {
            "/v2/accounts?limit=100": {"data": [{"id": "acc-usdc"}], "pagination": {"next_uri": None}},
            "/v2/accounts/acc-usdc/transactions?limit=100": {
                "data": [
                    {"id": "n1", "type": "interest", "status": "completed", "created_at": "2026-11-19T19:51:16Z",
                     "amount": {"amount": "0.002898", "currency": "USDC"}},
                    {"id": "n2", "type": "send", "status": "pending", "created_at": "2026-11-18T00:00:00Z",
                     "amount": {"amount": "1", "currency": "USDC"}},
                ],
                "pagination": {"next_uri": "/v2/accounts/acc-usdc/transactions?limit=100&starting_after=n2"},
            },
            "/v2/accounts/acc-usdc/transactions?limit=100&starting_after=n2": {
                "data": [
                    {"id": "o1", "type": "send", "status": "completed", "created_at": "2026-10-20T02:28:21Z",
                     "amount": {"amount": "3350", "currency": "USDC"}},
                ],
                "pagination": {"next_uri": "/v2/accounts/acc-usdc/transactions?limit=100&starting_after=o1"},
            },
        }
        get = AsyncMock(side_effect=lambda uri: pages[uri])
        with patch.object(p, "_get", get):
            txs, cursor = await p.sync_transactions(since="2026-11-20T00:00:00+00:00")
        assert cursor is None
        assert [t.source_tx_id for t in txs] == ["n1"]  # pending skipped, older than since-7d skipped
        # Stopped paging once a page reached rows older than the window.
        assert "/v2/accounts/acc-usdc/transactions?limit=100&starting_after=o1" not in [c.args[0] for c in get.call_args_list]

    @pytest.mark.asyncio
    async def test_jwt_uri_excludes_query_string(self, ed_key, monkeypatch):
        seen = {}

        class FakeResp:
            status_code = 200

            def json(self):
                return {"data": []}

        class FakeClient:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, headers):
                seen["url"], seen["auth"] = url, headers["Authorization"]
                return FakeResp()

        monkeypatch.setattr(cb.httpx, "AsyncClient", FakeClient)
        await CoinbaseProvider()._get("/v2/accounts/x/transactions?limit=100&starting_after=y")
        claims = json.loads(_pad(seen["auth"].split(" ")[1].split(".")[1]))
        assert seen["url"] == "https://api.coinbase.com/v2/accounts/x/transactions?limit=100&starting_after=y"
        assert claims["uri"] == "GET api.coinbase.com/v2/accounts/x/transactions"
