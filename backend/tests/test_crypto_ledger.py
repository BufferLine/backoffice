"""
E2E: accrual ledger for a USD invoice paid in USDC and off-ramped to SGD.

Flow under test:
1. Map ledger accounts (receivable USD/SGD, revenue, FX gain/loss).
2. Issue a USD invoice at 1.2934 → Dr Receivable-USD / Cr Revenue (SGD 4,850.25).
3. Receive USDC 3,750 at 1.3000 → Dr Coinbase USDC / Cr Receivable-USD, FX gain SGD 24.75; invoice paid.
4. Convert USDC 3,750 → SGD 4,800.00 landing as a synced Aspire deposit
   → Cr USDC at carrying 1.3000 (SGD 4,875.00), FX loss SGD 75.00; deposit reconciled.
5. An SGD invoice paid by bank deposit settles its receivable on reconcile (no double revenue).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bank_transaction import BankTransaction
from app.models.company import CompanySettings
from tests.conftest import TestSessionLocal

ISSUE_RATE = "1.2934"
RECEIPT_RATE = "1.3000"
TX_HASH = "0x" + "c0ffee" * 10 + "abcd"
WALLET_ADDR = "0x" + "c0" * 20
BAD_TX = "0x" + "bad0" * 16  # the fake chain reports an amount mismatch for this one
OLD_TX = "0x" + "01d0" * 16  # mined long before any invoice was issued
INTERNAL_TX = "0x" + "1a1a" * 16  # sent from our own wallet
PAYER = "0x" + "aa" * 20

ids: dict[str, str] = {}
fake_chain_calls: list[dict] = []


@pytest.fixture(autouse=True)
def _fake_chain(monkeypatch):
    """No network in tests: the chain 'confirms' any transfer except BAD_TX."""
    from datetime import datetime, timezone

    from app.services import onchain

    async def fake_verify(chain, tx_hash, currency, to_address, expected_amount=None):
        fake_chain_calls.append({"chain": chain, "tx_hash": tx_hash, "to": to_address, "amount": expected_amount})
        ok = tx_hash != BAD_TX
        mined = datetime(2020, 1, 1, tzinfo=timezone.utc) if tx_hash == OLD_TX else datetime.now(timezone.utc)
        sender = WALLET_ADDR if tx_hash == INTERNAL_TX else PAYER
        return onchain.VerificationResult(
            verified=ok,
            chain=chain,
            tx_hash=tx_hash,
            currency=currency,
            token_contract=onchain.TOKENS[(chain, currency)].address,
            to_address=to_address,
            amount_to_us=expected_amount if ok else Decimal("1.00"),
            expected_amount=expected_amount,
            confirmations=100,
            min_confirmations=30,
            block_timestamp=mined,
            from_addresses=[sender],
            problems=[] if ok else [f"amount received 1.00 {currency} != expected {expected_amount}"],
        )

    monkeypatch.setattr(onchain, "verify_stablecoin_transfer", fake_verify)


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def _restore_ledger_mapping():
    """Other test modules issue invoices without a ledger mapping; leave none behind."""
    yield
    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        metadata = dict(company.metadata_json or {})
        metadata.pop("ledger_accounts", None)
        company.metadata_json = metadata
        await session.commit()


async def _account(client, headers, name, account_type, account_class, currency, wallet_address=None) -> str:
    resp = await client.post(
        "/api/accounts",
        json={
            "name": name,
            "account_type": account_type,
            "account_class": account_class,
            "currency": currency,
            "opening_balance_date": "2026-01-01",
            "wallet_address": wallet_address,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _journal(client, headers, entry_id) -> list[tuple[str, str, Decimal, Decimal, Decimal]]:
    resp = await client.get(f"/api/journal-entries/{entry_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return [
        (l["account_id"], l["currency"], Decimal(l["debit"]), Decimal(l["credit"]), Decimal(l["fx_rate_to_sgd"]))
        for l in resp.json()["lines"]
    ]


async def _invoice(client, headers, currency, price) -> str:
    resp = await client.post(
        "/api/invoices",
        json={"client_id": ids["client"], "currency": currency, "description": f"{currency} services"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    invoice_id = resp.json()["id"]
    resp = await client.post(
        f"/api/invoices/{invoice_id}/line-items",
        json={"description": "Protocol engineering", "quantity": "1", "unit_price": price},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return invoice_id


async def _bank_deposit(currency: str, amount: str, account_id: str, payment_id: str | None = None) -> str:
    async with TestSessionLocal() as session:
        tx = BankTransaction(
            id=uuid.uuid4(),
            source="aspire",
            source_tx_id=f"test-{uuid.uuid4()}",
            tx_date=date(2026, 11, 5),
            amount=Decimal(amount),
            currency=currency,
            counterparty="COINBASE SINGAPORE PTE. LTD.",
            match_status="manual_matched" if payment_id else "unmatched",
            matched_payment_id=uuid.UUID(payment_id) if payment_id else None,
            account_id=uuid.UUID(account_id),
        )
        session.add(tx)
        await session.commit()
        return str(tx.id)


@pytest.mark.asyncio
async def test_setup_accounts_and_mapping(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    ids["ar_usd"] = await _account(client, h, "Receivable USD", "virtual", "asset", "USD")
    ids["ar_sgd"] = await _account(client, h, "Receivable SGD", "virtual", "asset", "SGD")
    ids["revenue"] = await _account(client, h, "Revenue", "virtual", "revenue", "SGD")
    ids["fx"] = await _account(client, h, "FX gain/loss", "virtual", "revenue", "SGD")
    ids["usdc"] = await _account(client, h, "Coinbase USDC", "crypto_wallet", "asset", "USDC", WALLET_ADDR)
    ids["aspire"] = await _account(client, h, "Aspire SGD", "bank", "asset", "SGD")

    resp = await client.post(
        "/api/clients",
        json={"legal_name": "Stablecoin Client Ltd", "billing_email": "ap@client.test", "default_currency": "USD"},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    ids["client"] = resp.json()["id"]

    resp = await client.get("/api/ledger/accounts", headers=h)
    assert resp.status_code == 200 and resp.json()["configured"] is False

    # Wrong currency for a receivable is rejected.
    resp = await client.patch("/api/ledger/accounts", json={"receivable": {"USD": ids["ar_sgd"]}}, headers=h)
    assert resp.status_code == 422, resp.text

    resp = await client.patch(
        "/api/ledger/accounts",
        json={
            "receivable": {"USD": ids["ar_usd"], "SGD": ids["ar_sgd"]},
            "revenue": ids["revenue"],
            "fx_gain_loss": ids["fx"],
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["receivable"] == {"SGD": ids["ar_sgd"], "USD": ids["ar_usd"]}


@pytest.mark.asyncio
async def test_issue_usd_invoice_posts_receivable(client: AsyncClient, auth_headers: dict):
    ids["usd_invoice"] = await _invoice(client, auth_headers, "USD", "3750.00")
    resp = await client.post(
        f"/api/invoices/{ids['usd_invoice']}/issue",
        json={"fx_rate_to_sgd": ISSUE_RATE},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "issued"
    assert body["journal_entry_id"]

    lines = await _journal(client, auth_headers, body["journal_entry_id"])
    assert sorted(lines) == sorted([
        (ids["ar_usd"], "USD", Decimal("3750"), Decimal("0"), Decimal(ISSUE_RATE)),
        (ids["revenue"], "SGD", Decimal("0"), Decimal("4850.25"), Decimal("1")),
    ])


@pytest.mark.asyncio
async def test_issue_without_rate_fails_cleanly(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Without a rate and without Airwallex, a USD invoice cannot be issued (nothing is half-done)."""
    from app.config import settings

    monkeypatch.setattr(settings, "AIRWALLEX_CLIENT_ID", None)
    monkeypatch.setattr(settings, "AIRWALLEX_API_KEY", None)
    invoice_id = await _invoice(client, auth_headers, "USD", "10.00")
    resp = await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)
    assert resp.status_code == 422, resp.text
    assert "Airwallex" in resp.json()["detail"] or "fx_rate_to_sgd" in resp.json()["detail"]
    resp = await client.get(f"/api/invoices/{invoice_id}", headers=auth_headers)
    assert resp.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_receive_crypto_rejects_wrong_amount(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={
            "invoice_id": ids["usd_invoice"], "wallet_account_id": ids["usdc"],
            "amount": "3749.99", "currency": "USDC", "fx_rate_to_sgd": RECEIPT_RATE,
            "chain_id": "base", "tx_hash": "0x" + "01" * 32,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "does not equal invoice total" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_receive_crypto_rejects_failed_onchain_verification(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={
            "invoice_id": ids["usd_invoice"], "wallet_account_id": ids["usdc"], "amount": "3750.00",
            "currency": "USDC", "chain_id": "base", "tx_hash": BAD_TX, "fx_rate_to_sgd": RECEIPT_RATE,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "On-chain verification failed" in resp.json()["detail"]
    assert fake_chain_calls[-1]["to"] == WALLET_ADDR
    resp = await client.get(f"/api/invoices/{ids['usd_invoice']}", headers=auth_headers)
    assert resp.json()["status"] == "issued"  # nothing recorded


@pytest.mark.asyncio
async def test_receive_crypto_requires_chain_unless_skipped(client: AsyncClient, auth_headers: dict):
    base = {
        "invoice_id": ids["usd_invoice"], "wallet_account_id": ids["usdc"], "amount": "3750.00",
        "currency": "USDC", "tx_hash": TX_HASH, "fx_rate_to_sgd": RECEIPT_RATE,
    }
    resp = await client.post("/api/payments/receive-crypto", json=base, headers=auth_headers)
    assert resp.status_code == 409 and "chain is required" in resp.json()["detail"]
    resp = await client.post(
        "/api/payments/receive-crypto", json={**base, "skip_verification": True}, headers=auth_headers
    )
    assert resp.status_code == 409 and "skip_reason must explain" in resp.json()["detail"]
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={**base, "skip_verification": True, "skip_reason": "split"},
        headers=auth_headers,
    )
    assert resp.status_code == 409 and "at least 15" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_receive_crypto_settles_receivable_with_fx_gain(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={
            "invoice_id": ids["usd_invoice"],
            "wallet_account_id": ids["usdc"],
            "amount": "3750.00",
            "currency": "USDC",
            "tx_hash": TX_HASH,
            "chain_id": "base",
            "payment_date": "2026-11-05",
            "fx_rate_to_sgd": RECEIPT_RATE,
            "notes": "Verified on basescan",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    payment = resp.json()
    assert payment["payment_type"] == "crypto"
    assert payment["currency"] == "USDC"
    assert Decimal(payment["sgd_value"]) == Decimal("4875.00")
    assert payment["fx_rate_source"] == "manual"
    assert payment["journal_entry_id"]
    verification = payment["onchain_verification"]
    assert verification["verified"] is True
    assert verification["chain"] == "base" and verification["to_address"] == WALLET_ADDR
    assert verification["amount_to_us"] == "3750.00"

    lines = await _journal(client, auth_headers, payment["journal_entry_id"])
    assert sorted(lines) == sorted([
        (ids["usdc"], "USDC", Decimal("3750"), Decimal("0"), Decimal(RECEIPT_RATE)),
        (ids["ar_usd"], "USD", Decimal("0"), Decimal("3750"), Decimal(ISSUE_RATE)),
        (ids["fx"], "SGD", Decimal("0"), Decimal("24.75"), Decimal("1")),
    ])

    resp = await client.get(f"/api/invoices/{ids['usd_invoice']}", headers=auth_headers)
    assert resp.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_same_tx_hash_cannot_be_recorded_twice(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "USD", "1.00")
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"fx_rate_to_sgd": ISSUE_RATE}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={
            "invoice_id": invoice_id, "wallet_account_id": ids["usdc"], "amount": "1.00",
            "currency": "USDC", "tx_hash": TX_HASH.upper().replace("0X", "0x"), "chain_id": "base",
            "fx_rate_to_sgd": RECEIPT_RATE,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "tx_hash" in resp.json()["detail"]
    resp = await client.get(f"/api/invoices/{invoice_id}", headers=auth_headers)
    assert resp.json()["status"] == "issued"


@pytest.mark.asyncio
async def test_skip_verification_with_reason_is_recorded(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "USD", "2.00")
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"fx_rate_to_sgd": ISSUE_RATE}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    calls_before = len(fake_chain_calls)
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={
            "invoice_id": invoice_id, "wallet_account_id": ids["usdc"], "amount": "2.00", "currency": "USDC",
            "payment_date": "2026-11-05", "fx_rate_to_sgd": RECEIPT_RATE,
            "skip_verification": True, "skip_reason": "Client paid in two transfers; checked in Coinbase",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    # (a too-short reason is rejected; see test_receive_crypto_requires_chain_unless_skipped)
    assert len(fake_chain_calls) == calls_before  # chain not queried
    assert resp.json()["onchain_verification"] == {
        "skipped": True, "reason": "Client paid in two transfers; checked in Coinbase", "chain": None,
    }


@pytest.mark.asyncio
async def test_receipt_date_defaults_to_block_date_in_sgt(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "USD", "3.00")
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"fx_rate_to_sgd": ISSUE_RATE}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={
            "invoice_id": invoice_id, "wallet_account_id": ids["usdc"], "amount": "3.00", "currency": "USDC",
            "chain_id": "base", "tx_hash": "0x" + "02" * 32, "fx_rate_to_sgd": RECEIPT_RATE,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    from app.services.ledger import today_local

    assert resp.json()["payment_date"] == today_local().isoformat()  # the block's SGT date


@pytest.mark.asyncio
async def test_transfer_older_than_invoice_or_from_own_wallet_is_rejected(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "USD", "4.00")
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"fx_rate_to_sgd": ISSUE_RATE}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = {
        "invoice_id": invoice_id, "wallet_account_id": ids["usdc"], "amount": "4.00", "currency": "USDC",
        "chain_id": "base", "fx_rate_to_sgd": RECEIPT_RATE,
    }
    resp = await client.post("/api/payments/receive-crypto", json={**body, "tx_hash": OLD_TX}, headers=auth_headers)
    assert resp.status_code == 409 and "predates the invoice" in resp.json()["detail"]
    resp = await client.post(
        "/api/payments/receive-crypto", json={**body, "tx_hash": INTERNAL_TX}, headers=auth_headers
    )
    assert resp.status_code == 409 and "internal transfer" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_case_variant_tx_hash_is_a_duplicate_everywhere(client: AsyncClient, auth_headers: dict):
    upper = "0x" + TX_HASH[2:].upper()
    resp = await client.post(
        "/api/payments",
        json={"payment_type": "crypto", "currency": "USDC", "amount": "3750.00", "tx_hash": upper},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    resp = await client.post(
        "/api/payments",
        json={"payment_type": "crypto", "currency": "USDC", "amount": "3750.00", "tx_hash": TX_HASH[2:]},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text  # missing 0x is the same transaction


@pytest.mark.asyncio
async def test_unverified_crypto_payment_cannot_mark_invoice_paid(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "USD", "6.00")
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"fx_rate_to_sgd": ISSUE_RATE}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "crypto", "related_entity_type": "invoice", "related_entity_id": invoice_id,
            "currency": "USD", "amount": "6.00", "tx_hash": "0x" + "66" * 32,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    payment_id = resp.json()["id"]
    resp = await client.post(
        f"/api/invoices/{invoice_id}/mark-paid", json={"payment_id": payment_id}, headers=auth_headers
    )
    assert resp.status_code == 422 and "receive-crypto" in resp.json()["detail"]
    resp = await client.post(
        f"/api/payments/{payment_id}/link",
        json={"related_entity_type": "invoice", "related_entity_id": invoice_id},
        headers=auth_headers,
    )
    assert resp.status_code in (409, 422), resp.text
    assert "receive-crypto" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verified_wallet_address_is_immutable_and_audited(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/accounts/{ids['usdc']}", json={"wallet_address": "0x" + "99" * 20}, headers=auth_headers
    )
    assert resp.status_code == 409, resp.text
    assert "verified receipt" in resp.json()["detail"]

    # A wallet account with no receipts can change, is normalised, and the change is audited.
    other = await _account(client, auth_headers, "Spare USDC", "crypto_wallet", "asset", "USDC")
    resp = await client.patch(
        f"/api/accounts/{other}", json={"wallet_address": "0x" + "AB" * 20}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["wallet_address"] == "0x" + "ab" * 20
    from app.models.audit import AuditLog

    async with TestSessionLocal() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "account.wallet_change", AuditLog.entity_id == uuid.UUID(other))
            )
        ).scalars().all()
    assert len(rows) == 1

    resp = await client.patch(f"/api/accounts/{other}", json={"wallet_address": "0xnothex"}, headers=auth_headers)
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_accountant_cannot_set_wallets_or_skip_verification(client: AsyncClient, auth_headers: dict):
    from app.models.user import Role

    resp = await client.post(
        "/api/users/invite",
        json={"email": "acct-ledger@test.com", "name": "Accountant", "password": "acctpass123"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    async with TestSessionLocal() as session:
        role_id = (await session.execute(select(Role.id).where(Role.name == "accountant"))).scalar_one()
    resp = await client.post(f"/api/users/{user_id}/roles", json={"role_id": str(role_id)}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    # Mint the token directly: other modules exhaust the login rate limit in a full run.
    from app.services.auth import _DEFAULT_ROLES, create_access_token

    perms = next(p for name, _, p in _DEFAULT_ROLES if name == "accountant")
    assert "payment:manage_wallets" not in perms and "payment:skip_verification" not in perms
    acct = {"Authorization": f"Bearer {create_access_token(uuid.UUID(user_id), perms)}"}

    resp = await client.patch(f"/api/accounts/{ids['usdc']}", json={"wallet_address": PAYER}, headers=acct)
    assert resp.status_code == 403, resp.text
    resp = await client.post(
        "/api/accounts",
        json={"name": "Mine", "account_type": "crypto_wallet", "account_class": "asset", "currency": "USDC",
              "opening_balance_date": "2026-01-01", "wallet_address": PAYER},
        headers=acct,
    )
    assert resp.status_code == 403, resp.text
    resp = await client.post(
        "/api/payments/receive-crypto",
        json={"invoice_id": ids["usd_invoice"], "wallet_account_id": ids["usdc"], "amount": "1", "currency": "USDC",
              "skip_verification": True, "skip_reason": "accountant trying to skip"},
        headers=acct,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_verify_onchain_endpoint_is_read_only(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/payments/verify-onchain",
        json={"chain": "base", "tx_hash": BAD_TX, "currency": "USDC", "wallet_account_id": ids["usdc"],
              "expected_amount": "5"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verified"] is False and body["problems"]
    resp = await client.post(
        "/api/payments/verify-onchain",
        json={"chain": "base", "tx_hash": BAD_TX, "currency": "USDC", "wallet_account_id": ids["ar_usd"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # account has no wallet_address


@pytest.mark.asyncio
async def test_off_ramp_conversion_books_fx_loss_and_reconciles_deposit(client: AsyncClient, auth_headers: dict):
    deposit_id = await _bank_deposit("SGD", "4800.00", ids["aspire"])

    # A deposit amount that does not match the bought side is rejected.
    bad = await client.post(
        "/api/fx-conversions",
        json={
            "conversion_date": "2026-11-05", "sell_currency": "USDC", "sell_amount": "3750.00",
            "buy_currency": "SGD", "buy_amount": "4799.00", "sell_account_id": ids["usdc"],
            "buy_account_id": ids["aspire"], "bank_transaction_id": deposit_id,
        },
        headers=auth_headers,
    )
    assert bad.status_code in (409, 422), bad.text

    resp = await client.post(
        "/api/fx-conversions",
        json={
            "conversion_date": "2026-11-05",
            "sell_currency": "USDC",
            "sell_amount": "3750.00",
            "buy_currency": "SGD",
            "buy_amount": "4800.00",
            "sell_account_id": ids["usdc"],
            "buy_account_id": ids["aspire"],
            "bank_transaction_id": deposit_id,
            "provider": "coinbase",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    conversion = resp.json()
    assert conversion["bank_transaction_id"] == deposit_id

    lines = await _journal(client, auth_headers, conversion["journal_entry_id"])
    assert sorted(lines) == sorted([
        (ids["aspire"], "SGD", Decimal("4800"), Decimal("0"), Decimal("1")),
        (ids["usdc"], "USDC", Decimal("0"), Decimal("3750"), Decimal(RECEIPT_RATE)),  # carrying rate
        (ids["fx"], "SGD", Decimal("75"), Decimal("0"), Decimal("1")),  # 4875 - 4800
    ])

    resp = await client.get(f"/api/bank-transactions/{deposit_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["match_status"] == "reconciled"

    # The same deposit cannot be reconciled again through bank reconciliation.
    resp = await client.post(
        f"/api/bank-transactions/{deposit_id}/reconcile",
        json={"bank_account_id": ids["aspire"], "contra_account_id": ids["revenue"]},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_trial_balance_after_off_ramp(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/journal-entries/trial-balance", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    rows = {r["account_id"]: r for r in resp.json()["rows"]}
    # 3,750 USDC sold; the 2.00 + 3.00 USDC received in later receipts are still held
    assert Decimal(rows[ids["usdc"]]["balance"]) == Decimal("5")
    assert Decimal(rows[ids["usdc"]]["balance_sgd"]) == Decimal("6.50")  # 5 @ 1.30
    # Still open: 1.00 (duplicate tx), 4.00 (stale/internal tx rejected), 6.00 (unverified payment refused)
    assert Decimal(rows[ids["ar_usd"]]["balance"]) == Decimal("11.00")
    assert Decimal(rows[ids["aspire"]]["total_debit"]) == Decimal("4800")
    # FX: gains 24.75 + 0.01 + 0.02 on receipts, loss 75.00 on off-ramp → net loss 50.22
    assert Decimal(rows[ids["fx"]]["balance_sgd"]) == Decimal("50.22")
    # Mixed USD/USDC/SGD books balance in SGD (native sums would not).
    body = resp.json()
    assert body["is_balanced"] is True, body
    assert Decimal(body["total_debit_sgd"]) == Decimal(body["total_credit_sgd"])


@pytest.mark.asyncio
async def test_deposit_for_crypto_settled_invoice_is_not_settled_twice(client: AsyncClient, auth_headers: dict):
    """A USDC statement line matched to the receive-crypto payment must not credit the receivable again."""
    resp = await client.get("/api/payments", params={"entity_type": "invoice", "per_page": 100}, headers=auth_headers)
    crypto = next(p for p in resp.json()["items"] if p["tx_hash"] == TX_HASH)
    deposit_id = await _bank_deposit("USDC", "3750.00", ids["usdc"], payment_id=crypto["id"])
    resp = await client.post(
        f"/api/bank-transactions/{deposit_id}/reconcile",
        json={"bank_account_id": ids["usdc"], "fx_rate_to_sgd": RECEIPT_RATE},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "already settled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_bank_paid_sgd_invoice_settles_receivable(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "SGD", "500.00")
    resp = await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["journal_entry_id"]

    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer", "related_entity_type": "invoice", "related_entity_id": invoice_id,
            "currency": "SGD", "amount": "500.00", "payment_date": "2026-11-05",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    payment_id = resp.json()["id"]
    deposit_id = await _bank_deposit("SGD", "500.00", ids["aspire"], payment_id=payment_id)

    # Booking it against revenue again would double-count: rejected.
    resp = await client.post(
        f"/api/bank-transactions/{deposit_id}/reconcile",
        json={"bank_account_id": ids["aspire"], "contra_account_id": ids["revenue"]},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "receivable" in resp.json()["detail"]

    # Contra omitted → settles the SGD receivable.
    resp = await client.post(
        f"/api/bank-transactions/{deposit_id}/reconcile",
        json={"bank_account_id": ids["aspire"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["match_status"] == "reconciled"

    resp = await client.get(f"/api/payments/{payment_id}", headers=auth_headers)
    lines = await _journal(client, auth_headers, resp.json()["journal_entry_id"])
    assert sorted(lines) == sorted([
        (ids["aspire"], "SGD", Decimal("500"), Decimal("0"), Decimal("1")),
        (ids["ar_sgd"], "SGD", Decimal("0"), Decimal("500"), Decimal("1")),
    ])


@pytest.mark.asyncio
async def test_deposit_for_cancelled_invoice_needs_explicit_contra(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "SGD", "120.00")
    assert (await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)).status_code == 200
    assert (await client.post(f"/api/invoices/{invoice_id}/cancel", headers=auth_headers)).status_code == 200
    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer", "related_entity_type": "invoice", "related_entity_id": invoice_id,
            "currency": "SGD", "amount": "120.00", "payment_date": "2026-11-05",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    deposit_id = await _bank_deposit("SGD", "120.00", ids["aspire"], payment_id=resp.json()["id"])
    resp = await client.post(
        f"/api/bank-transactions/{deposit_id}/reconcile",
        json={"bank_account_id": ids["aspire"]},
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "cancelled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_issued_invoice_reverses_receivable(client: AsyncClient, auth_headers: dict):
    invoice_id = await _invoice(client, auth_headers, "SGD", "200.00")
    resp = await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"/api/invoices/{invoice_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/journal-entries", params={"per_page": 100}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    reversals = [
        e for e in resp.json()["items"]
        if e["source_type"] == "invoice_cancel" and e["source_id"] == invoice_id
    ]
    assert len(reversals) == 1
    assert sorted(
        (l["account_id"], Decimal(l["debit"]), Decimal(l["credit"])) for l in reversals[0]["lines"]
    ) == sorted([
        (ids["ar_sgd"], Decimal("0"), Decimal("200")),
        (ids["revenue"], Decimal("200"), Decimal("0")),
    ])


@pytest.mark.asyncio
async def test_post_journal_backfills_issued_invoice(client: AsyncClient, auth_headers: dict):
    # Issue with the mapping temporarily removed, then backfill.
    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        saved = dict(company.metadata_json or {})
        company.metadata_json = {k: v for k, v in saved.items() if k != "ledger_accounts"}
        await session.commit()

    invoice_id = await _invoice(client, auth_headers, "SGD", "300.00")
    resp = await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["journal_entry_id"] is None

    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        company.metadata_json = saved
        await session.commit()

    resp = await client.post(f"/api/invoices/{invoice_id}/post-journal", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["journal_entry_id"]

    resp = await client.post(f"/api/invoices/{invoice_id}/post-journal", headers=auth_headers)
    assert resp.status_code == 409, resp.text  # already posted


@pytest.mark.asyncio
async def test_post_journal_refuses_when_revenue_was_booked_at_reconcile(client: AsyncClient, auth_headers: dict):
    """Pre-accrual flow: deposit reconciled straight to revenue; a later backfill would double revenue."""
    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        saved = dict(company.metadata_json or {})
        company.metadata_json = {k: v for k, v in saved.items() if k != "ledger_accounts"}
        await session.commit()

    invoice_id = await _invoice(client, auth_headers, "SGD", "80.00")
    assert (await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)).status_code == 200
    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer", "related_entity_type": "invoice", "related_entity_id": invoice_id,
            "currency": "SGD", "amount": "80.00", "payment_date": "2026-11-05",
        },
        headers=auth_headers,
    )
    deposit_id = await _bank_deposit("SGD", "80.00", ids["aspire"], payment_id=resp.json()["id"])
    resp = await client.post(
        f"/api/bank-transactions/{deposit_id}/reconcile",
        json={"bank_account_id": ids["aspire"], "contra_account_id": ids["revenue"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        company.metadata_json = saved
        await session.commit()

    resp = await client.post(f"/api/invoices/{invoice_id}/post-journal", headers=auth_headers)
    assert resp.status_code == 409, resp.text
    assert "double-count" in resp.json()["detail"]
