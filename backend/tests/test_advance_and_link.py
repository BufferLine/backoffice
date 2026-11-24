"""E2E: settle invoices from customer advances (IFRIC 22) and link bank rows to one journal entry."""

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

ids: dict[str, str] = {}
ISSUE_RATE = "1.2865"


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def _restore_ledger_mapping():
    yield
    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        metadata = dict(company.metadata_json or {})
        metadata.pop("ledger_accounts", None)
        company.metadata_json = metadata
        await session.commit()


async def _account(client, h, name, kind, cls, ccy):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "account_type": kind, "account_class": cls, "currency": ccy,
              "opening_balance_date": "2026-01-01"},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _post(client, h, entry_date, description, lines, confirmed=True):
    resp = await client.post(
        "/api/journal-entries",
        json={"entry_date": entry_date, "description": description, "is_confirmed": confirmed, "lines": lines},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _line(account, *, debit="0", credit="0", ccy, rate):
    return {"account_id": account, "debit": debit, "credit": credit, "currency": ccy, "fx_rate_to_sgd": rate}


async def _journal_lines(client, h, entry_id):
    resp = await client.get(f"/api/journal-entries/{entry_id}", headers=h)
    assert resp.status_code == 200, resp.text
    return sorted(
        (l["account_id"], l["currency"], Decimal(l["debit"]), Decimal(l["credit"])) for l in resp.json()["lines"]
    )


async def _issued_invoice(client, h, price, number=None):
    body = {"client_id": ids["client"], "currency": "USD", "description": "Retainer"}
    resp = await client.post("/api/invoices", json=body, headers=h)
    assert resp.status_code == 201, resp.text
    inv = resp.json()["id"]
    assert (await client.post(
        f"/api/invoices/{inv}/line-items", json={"description": "Retainer", "quantity": "1", "unit_price": price}, headers=h
    )).status_code == 201
    resp = await client.post(f"/api/invoices/{inv}/issue", json={"fx_rate_to_sgd": ISSUE_RATE}, headers=h)
    assert resp.status_code == 200, resp.text
    return inv


@pytest.mark.asyncio
async def test_setup(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    ids["ar"] = await _account(client, h, "AA Receivable USD", "virtual", "asset", "USD")
    ids["rev"] = await _account(client, h, "AA Revenue", "virtual", "revenue", "SGD")
    ids["fx"] = await _account(client, h, "AA FX", "virtual", "expense", "SGD")
    ids["adv"] = await _account(client, h, "AA Customer advances", "virtual", "liability", "USD")
    ids["held"] = await _account(client, h, "AA Director-held USDT", "virtual", "asset", "USDT")
    ids["cb_usdt"] = await _account(client, h, "AA Coinbase USDT", "crypto_wallet", "asset", "USDT")
    ids["cb_usdc"] = await _account(client, h, "AA Coinbase USDC", "crypto_wallet", "asset", "USDC")
    resp = await client.patch(
        "/api/ledger/accounts",
        json={"receivable": {"USD": ids["ar"]}, "revenue": ids["rev"], "fx_gain_loss": ids["fx"]},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/clients", json={"legal_name": "Advance Client Inc.", "default_currency": "USD", "payment_terms_days": 0},
        headers=h,
    )
    ids["client"] = resp.json()["id"]

    # Two prepayments received before any invoice, at their own dates' rates.
    for d, rate in (("2026-04-03", "1.2871"), ("2026-05-05", "1.2772")):
        await _post(client, h, d, f"Prepayment {d}", [
            _line(ids["held"], debit="3060", ccy="USDT", rate=rate),
            _line(ids["adv"], credit="3060", ccy="USD", rate=rate),
        ])


@pytest.mark.asyncio
async def test_apply_advance_settles_invoice_at_advance_rate(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    inv = await _issued_invoice(client, h, "6120.00")
    # SGD value of the two advances at their receipt-date rates: 3938.53 + 3908.23
    resp = await client.post(
        f"/api/invoices/{inv}/apply-advance",
        json={"advance_account_id": ids["adv"], "advance_sgd_value": "7846.76", "notes": "Prepaid via Binance Pay"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "paid"

    payments = (await client.get("/api/payments", params={"entity_type": "invoice", "per_page": 100}, headers=h)).json()["items"]
    pay = next(p for p in payments if p["related_entity_id"] == inv)
    assert pay["payment_type"] == "advance" and Decimal(pay["amount"]) == Decimal("6120")
    lines = await _journal_lines(client, h, pay["journal_entry_id"])
    # rate 7846.76/6120 = 1.282150 → 7846.76; receivable 6120 @1.2865 = 7873.38; revenue reduced by 26.62
    assert lines == sorted([
        (ids["adv"], "USD", Decimal("6120"), Decimal("0")),
        (ids["ar"], "USD", Decimal("0"), Decimal("6120")),
        (ids["rev"], "SGD", Decimal("26.62"), Decimal("0")),
    ])

    again = await client.post(f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": ids["adv"]}, headers=h)
    assert again.status_code == 409, again.text


@pytest.mark.asyncio
async def test_apply_advance_guards(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    inv = await _issued_invoice(client, h, "100.00")
    # Advance account fully used by the previous invoice.
    resp = await client.post(f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": ids["adv"]}, headers=h)
    assert resp.status_code == 409 and "less than invoice total" in resp.json()["detail"]
    # Not a liability in the invoice currency.
    resp = await client.post(f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": ids["held"]}, headers=h)
    assert resp.status_code == 409, resp.text
    assert (await client.get(f"/api/invoices/{inv}", headers=h)).json()["status"] == "issued"


async def _fill_rows(order_id: str):
    """One USDT→USDC order filled in two parts: 4 Coinbase rows across two accounts."""
    async with TestSessionLocal() as session:
        made = []
        for acct, amount, ccy in (
            (ids["cb_usdt"], "-1000.00", "USDT"), (ids["cb_usdc"], "998.90", "USDC"),
            (ids["cb_usdt"], "-500.00", "USDT"), (ids["cb_usdc"], "499.45", "USDC"),
        ):
            tx = BankTransaction(
                id=uuid.uuid4(), source="coinbase", source_tx_id=f"fill-{uuid.uuid4()}", tx_date=date(2026, 10, 20),
                amount=Decimal(amount), currency=ccy, match_status="unmatched", account_id=uuid.UUID(acct),
                raw_data_json={"type": "advanced_trade_fill", "advanced_trade_fill": {"order_id": order_id, "product_id": "USDT-USDC"}},
            )
            session.add(tx)
            made.append(str(tx.id))
        await session.commit()
        return made


@pytest.mark.asyncio
async def test_link_coinbase_order_fills_to_one_entry(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    rows = await _fill_rows("order-A")
    entry = await _post(client, h, "2026-10-20", "Coinbase order-A USDT→USDC", [
        _line(ids["cb_usdc"], debit="1498.35", ccy="USDC", rate="1.2785"),
        _line(ids["cb_usdt"], credit="1500.00", ccy="USDT", rate="1.2785"),
        _line(ids["fx"], debit="2.11", ccy="SGD", rate="1"),
    ])
    resp = await client.post(
        "/api/bank-transactions/link", json={"journal_entry_id": entry, "coinbase_order_ids": ["order-A"]}, headers=h
    )
    assert resp.status_code == 200, resp.text
    linked = resp.json()["linked"]
    assert sorted(t["id"] for t in linked) == sorted(rows)
    assert all(t["match_status"] == "reconciled" and t["journal_entry_id"] == entry for t in linked)

    # Already reconciled rows cannot be linked again.
    resp = await client.post("/api/bank-transactions/link", json={"journal_entry_id": entry, "tx_ids": rows[:1]}, headers=h)
    assert resp.status_code == 409 and "already reconciled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_link_rejects_partial_or_mismatched_sets(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    rows = await _fill_rows("order-B")
    entry = await _post(client, h, "2026-10-20", "Coinbase order-B", [
        _line(ids["cb_usdc"], debit="1498.35", ccy="USDC", rate="1.2785"),
        _line(ids["cb_usdt"], credit="1500.00", ccy="USDT", rate="1.2785"),
        _line(ids["fx"], debit="2.11", ccy="SGD", rate="1"),
    ])
    # Only half the fills: totals don't match the entry.
    resp = await client.post("/api/bank-transactions/link", json={"journal_entry_id": entry, "tx_ids": rows[:2]}, headers=h)
    assert resp.status_code == 409 and "complete set" in resp.json()["detail"]
    # Unconfirmed entry.
    draft = await _post(client, h, "2026-10-20", "draft", [
        _line(ids["cb_usdc"], debit="1", ccy="USDC", rate="1.2785"),
        _line(ids["cb_usdt"], credit="1", ccy="USDT", rate="1.2785"),
    ], confirmed=False)
    resp = await client.post("/api/bank-transactions/link", json={"journal_entry_id": draft, "coinbase_order_ids": ["order-B"]}, headers=h)
    assert resp.status_code == 409 and "Confirm the journal entry" in resp.json()["detail"]
    # Nothing selected.
    resp = await client.post("/api/bank-transactions/link", json={"journal_entry_id": entry}, headers=h)
    assert resp.status_code == 409
    async with TestSessionLocal() as session:
        statuses = {t.match_status for t in (await session.execute(select(BankTransaction).where(BankTransaction.id.in_([uuid.UUID(r) for r in rows])))).scalars()}
    assert statuses == {"unmatched"}


@pytest.mark.asyncio
async def test_apply_advance_default_rate_dates_and_guards(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    adv2 = await _account(client, h, "AA Advances 2", "virtual", "liability", "USD")
    await _post(client, h, "2026-06-03", "Prepayment", [
        _line(ids["held"], debit="1000", ccy="USDT", rate="1.2821"),
        _line(adv2, credit="1000", ccy="USD", rate="1.2821"),
    ])
    inv = await _issued_invoice(client, h, "1000.00")
    issue_date = (await client.get(f"/api/invoices/{inv}", headers=h)).json()["issue_date"]

    # Settlement cannot precede the invoice.
    resp = await client.post(
        f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": adv2, "payment_date": "2020-01-01"}, headers=h
    )
    assert resp.status_code == 409 and "before the invoice issue date" in resp.json()["detail"]
    # A wildly wrong SGD value is rejected.
    resp = await client.post(
        f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": adv2, "advance_sgd_value": "1"}, headers=h
    )
    assert resp.status_code == 409, resp.text

    # Default: average carrying rate, settled on the issue date.
    resp = await client.post(f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": adv2}, headers=h)
    assert resp.status_code == 200, resp.text
    payments = (await client.get("/api/payments", params={"entity_type": "invoice", "per_page": 100}, headers=h)).json()["items"]
    pay = next(p for p in payments if p["related_entity_id"] == inv)
    assert pay["payment_date"] == issue_date
    lines = await _journal_lines(client, h, pay["journal_entry_id"])
    # 1000 @1.2821 = 1282.10 vs receivable 1000 @1.2865 = 1286.50 → revenue -4.40
    assert (ids["rev"], "SGD", Decimal("4.40"), Decimal("0")) in lines


@pytest.mark.asyncio
async def test_apply_advance_unrated_lines_need_explicit_value(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    adv3 = await _account(client, h, "AA Advances 3", "virtual", "liability", "USD")
    usd_bank = await _account(client, h, "AA USD bank", "bank", "asset", "USD")
    # A USD deposit reconciled without a rate (single-currency entry).
    resp = await client.post(
        "/api/journal-entries",
        json={"entry_date": "2026-07-01", "is_confirmed": True, "lines": [
            {"account_id": usd_bank, "debit": "500", "credit": "0", "currency": "USD"},
            {"account_id": adv3, "debit": "0", "credit": "500", "currency": "USD"},
        ]},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    inv = await _issued_invoice(client, h, "500.00")
    resp = await client.post(f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": adv3}, headers=h)
    assert resp.status_code == 409 and "without an SGD rate" in resp.json()["detail"]
    resp = await client.post(
        f"/api/invoices/{inv}/apply-advance", json={"advance_account_id": adv3, "advance_sgd_value": "641.00"}, headers=h
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_link_cannot_reuse_an_entry_or_net_off(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    rows_c = await _fill_rows("order-C")
    entry = await _post(client, h, "2026-10-20", "Coinbase order-C", [
        _line(ids["cb_usdc"], debit="1498.35", ccy="USDC", rate="1.2785"),
        _line(ids["cb_usdt"], credit="1500.00", ccy="USDT", rate="1.2785"),
        _line(ids["fx"], debit="2.11", ccy="SGD", rate="1"),
    ])
    assert (await client.post("/api/bank-transactions/link",
                              json={"journal_entry_id": entry, "coinbase_order_ids": ["order-C"]}, headers=h)).status_code == 200
    # An identical second order cannot be linked to the same entry.
    await _fill_rows("order-D")
    resp = await client.post("/api/bank-transactions/link",
                             json={"journal_entry_id": entry, "coinbase_order_ids": ["order-D"]}, headers=h)
    assert resp.status_code == 409 and "link exactly the complete set" in resp.json()["detail"]

    # Offsetting rows cannot be explained by an entry that nets to zero on the account.
    zero = await _post(client, h, "2026-10-20", "self-offsetting", [
        _line(ids["cb_usdt"], debit="1", ccy="USDT", rate="1.2785"),
        _line(ids["cb_usdt"], credit="1", ccy="USDT", rate="1.2785"),
    ])
    async with TestSessionLocal() as session:
        pair = []
        for amount in ("50000", "-50000"):
            tx = BankTransaction(id=uuid.uuid4(), source="coinbase", source_tx_id=f"x-{uuid.uuid4()}",
                                 tx_date=date(2026, 10, 20), amount=Decimal(amount), currency="USDT",
                                 match_status="unmatched", account_id=uuid.UUID(ids["cb_usdt"]))
            session.add(tx)
            pair.append(str(tx.id))
        await session.commit()
    resp = await client.post("/api/bank-transactions/link", json={"journal_entry_id": zero, "tx_ids": pair}, headers=h)
    assert resp.status_code == 409, resp.text
