"""E2E: retroactive invoices — fixed invoice numbers and back-dated issue (invoice:backdate)."""

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.company import CompanySettings
from app.services.ledger import today_local
from tests.conftest import TestSessionLocal

ids: dict[str, str] = {}


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")
async def _restore_ledger_mapping():
    yield
    async with TestSessionLocal() as session:
        company = (await session.execute(select(CompanySettings).limit(1))).scalar_one()
        metadata = dict(company.metadata_json or {})
        metadata.pop("ledger_accounts", None)
        company.metadata_json = metadata
        await session.commit()


async def _account(client, headers, name, cls, ccy):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "account_type": "virtual", "account_class": cls, "currency": ccy,
              "opening_balance_date": "2026-01-01"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _draft(client, headers, number=None, currency="USD", price="3060.00"):
    body = {"client_id": ids["client"], "currency": currency, "description": "Monthly development fee"}
    if number:
        body["invoice_number"] = number
    resp = await client.post("/api/invoices", json=body, headers=headers)
    if resp.status_code != 201:
        return resp
    invoice_id = resp.json()["id"]
    item = await client.post(
        f"/api/invoices/{invoice_id}/line-items",
        json={"description": "Development and maintenance — Apr 2026", "quantity": "1", "unit_price": price},
        headers=headers,
    )
    assert item.status_code == 201, item.text
    return resp


async def _accountant_headers(client, admin_headers):
    from app.models.user import Role
    from app.services.auth import _DEFAULT_ROLES, create_access_token

    resp = await client.post(
        "/api/users/invite",
        json={"email": f"acct-{uuid.uuid4().hex[:6]}@test.com", "name": "Accountant", "password": "acctpass123"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    async with TestSessionLocal() as session:
        role_id = (await session.execute(select(Role.id).where(Role.name == "accountant"))).scalar_one()
    assert (await client.post(f"/api/users/{user_id}/roles", json={"role_id": str(role_id)}, headers=admin_headers)).status_code == 200
    perms = next(p for name, _, p in _DEFAULT_ROLES if name == "accountant")
    assert "invoice:backdate" not in perms
    return {"Authorization": f"Bearer {create_access_token(uuid.UUID(user_id), perms)}"}


@pytest.mark.asyncio
async def test_setup(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/clients",
        json={"legal_name": "Backdate Client Inc.", "billing_email": "ap@backdate.test", "default_currency": "USD",
              "payment_terms_days": 14},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    ids["client"] = resp.json()["id"]
    ar = await _account(client, auth_headers, "BD Receivable USD", "asset", "USD")
    rev = await _account(client, auth_headers, "BD Revenue", "revenue", "SGD")
    resp = await client.patch("/api/ledger/accounts", json={"receivable": {"USD": ar}, "revenue": rev}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    ids["ar"] = ar


@pytest.mark.asyncio
async def test_fixed_invoice_number(client: AsyncClient, auth_headers: dict):
    resp = await _draft(client, auth_headers, number="BL-2026-001")
    assert resp.status_code == 201, resp.text
    assert resp.json()["invoice_number"] == "BL-2026-001"
    ids["inv1"] = resp.json()["id"]

    dup = await client.post(
        "/api/invoices",
        json={"client_id": ids["client"], "currency": "USD", "invoice_number": "BL-2026-001"},
        headers=auth_headers,
    )
    assert dup.status_code == 409 and "already exists" in dup.json()["detail"]

    bad = await client.post(
        "/api/invoices",
        json={"client_id": ids["client"], "currency": "USD", "invoice_number": "BL 2026 #1"},
        headers=auth_headers,
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_backdated_issue_sets_dates_and_posting_date(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/invoices/{ids['inv1']}/issue",
        json={"issue_date": "2026-04-01", "fx_rate_to_sgd": "1.3412"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["issue_date"] == "2026-04-01"
    assert body["due_date"] == "2026-04-15"  # client terms: 14 days from the issue date
    assert body["journal_entry_id"]

    entry = (await client.get(f"/api/journal-entries/{body['journal_entry_id']}", headers=auth_headers)).json()
    assert entry["entry_date"] == "2026-04-01"
    ar_line = next(l for l in entry["lines"] if l["account_id"] == ids["ar"])
    assert ar_line["fx_rate_to_sgd"].startswith("1.3412")

    async with TestSessionLocal() as session:
        log = (
            await session.execute(
                select(AuditLog).where(AuditLog.entity_id == uuid.UUID(ids["inv1"]), AuditLog.action == "issue_backdated")
            )
        ).scalar_one()
    assert log.output_json["issue_date"] == "2026-04-01" and log.output_json["backdated"] is True


@pytest.mark.asyncio
async def test_backdated_foreign_invoice_needs_rate(client: AsyncClient, auth_headers: dict, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "AIRWALLEX_CLIENT_ID", None)
    resp = await _draft(client, auth_headers)
    invoice_id = resp.json()["id"]
    resp = await client.post(f"/api/invoices/{invoice_id}/issue", json={"issue_date": "2026-05-01"}, headers=auth_headers)
    assert resp.status_code == 422 and "fx_rate_to_sgd is required" in resp.json()["detail"]
    assert (await client.get(f"/api/invoices/{invoice_id}", headers=auth_headers)).json()["status"] == "draft"


@pytest.mark.asyncio
async def test_future_issue_date_rejected(client: AsyncClient, auth_headers: dict):
    resp = await _draft(client, auth_headers)
    invoice_id = resp.json()["id"]
    future = (today_local() + timedelta(days=3)).isoformat()
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"issue_date": future, "fx_rate_to_sgd": "1.30"}, headers=auth_headers
    )
    assert resp.status_code == 422 and "in the future" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_accountant_cannot_backdate_or_fix_numbers(client: AsyncClient, auth_headers: dict):
    acct = await _accountant_headers(client, auth_headers)
    resp = await client.post(
        "/api/invoices",
        json={"client_id": ids["client"], "currency": "USD", "invoice_number": "BL-2026-099"},
        headers=acct,
    )
    assert resp.status_code == 403, resp.text

    resp = await _draft(client, acct)
    assert resp.status_code == 201, resp.text
    invoice_id = resp.json()["id"]
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue", json={"issue_date": "2026-04-01", "fx_rate_to_sgd": "1.30"}, headers=acct
    )
    assert resp.status_code == 403, resp.text
    # Today's date is not back-dating, so it is allowed.
    resp = await client.post(
        f"/api/invoices/{invoice_id}/issue",
        json={"issue_date": today_local().isoformat(), "fx_rate_to_sgd": "1.30"},
        headers=acct,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["issue_date"] == today_local().isoformat()
