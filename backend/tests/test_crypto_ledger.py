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

ids: dict[str, str] = {}


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


async def _account(client, headers, name, account_type, account_class, currency) -> str:
    resp = await client.post(
        "/api/accounts",
        json={
            "name": name,
            "account_type": account_type,
            "account_class": account_class,
            "currency": currency,
            "opening_balance_date": "2026-01-01",
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
    ids["usdc"] = await _account(client, h, "Coinbase USDC", "crypto_wallet", "asset", "USDC")
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
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "does not equal invoice total" in resp.json()["detail"]


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
            "currency": "USDC", "tx_hash": TX_HASH, "fx_rate_to_sgd": RECEIPT_RATE,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "tx_hash" in resp.json()["detail"]
    resp = await client.get(f"/api/invoices/{invoice_id}", headers=auth_headers)
    assert resp.json()["status"] == "issued"


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
    # USDC fully sold, receivable fully settled; net FX = +24.75 - 75.00 = -50.25
    assert Decimal(rows[ids["usdc"]]["balance"]) == 0
    assert Decimal(rows[ids["ar_usd"]]["balance"]) == Decimal("1.00")  # the 1.00 invoice above is still open
    assert Decimal(rows[ids["aspire"]]["total_debit"]) == Decimal("4800")
    # Net FX: gain 24.75 on receipt, loss 75.00 on off-ramp → net debit (loss) 50.25
    assert Decimal(rows[ids["fx"]]["balance_sgd"]) == Decimal("50.25")
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
