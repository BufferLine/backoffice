"""E2E: a paid invoice's PDF can be regenerated (marked PAID) and payment notes can be edited."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.changelog import ChangeLog
from app.models.invoice import Invoice
from tests.conftest import TestSessionLocal

ids: dict[str, str] = {}


async def _pdf_file_id(invoice_id: str) -> str:
    async with TestSessionLocal() as session:
        inv = (await session.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))).scalar_one()
        return str(inv.issued_pdf_file_id)


@pytest.mark.asyncio
async def test_setup_paid_invoice(client: AsyncClient, auth_headers: dict):
    h = auth_headers
    resp = await client.post(
        "/api/clients",
        json={"legal_name": "Paid PDF Client Inc.", "billing_email": "ap@paidpdf.test", "default_currency": "SGD"},
        headers=h,
    )
    assert resp.status_code == 201, resp.text
    inv = (await client.post(
        "/api/invoices", json={"client_id": resp.json()["id"], "currency": "SGD", "description": "Retainer"}, headers=h
    )).json()["id"]
    assert (await client.post(
        f"/api/invoices/{inv}/line-items", json={"description": "Retainer", "quantity": "1", "unit_price": "500"}, headers=h
    )).status_code == 201
    issued = await client.post(f"/api/invoices/{inv}/issue", headers=h)
    assert issued.status_code == 200, issued.text
    ids["inv"], ids["issued_pdf"] = inv, await _pdf_file_id(inv)

    pay = await client.post(
        "/api/payments",
        json={"payment_type": "bank_transfer", "currency": "SGD", "amount": "500", "payment_date": "2026-11-20",
              "notes": "old note"},
        headers=h,
    )
    assert pay.status_code == 201, pay.text
    ids["pay"] = pay.json()["id"]
    link = await client.post(
        f"/api/payments/{ids['pay']}/link", json={"related_entity_type": "invoice", "related_entity_id": inv}, headers=h
    )
    assert link.status_code == 200, link.text
    assert (await client.get(f"/api/invoices/{inv}", headers=h)).json()["status"] == "paid"


@pytest.mark.asyncio
async def test_update_payment_notes_is_tracked(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/payments/{ids['pay']}/notes", json={"notes": "  Received 20 Nov 2026 by FAST  "}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["notes"] == "Received 20 Nov 2026 by FAST"
    assert resp.json()["amount"].startswith("500")

    async with TestSessionLocal() as session:
        change = (await session.execute(
            select(ChangeLog).where(ChangeLog.entity_id == uuid.UUID(ids["pay"]), ChangeLog.field_name == "notes")
        )).scalar_one()
        audit = (await session.execute(
            select(AuditLog).where(AuditLog.entity_id == uuid.UUID(ids["pay"]), AuditLog.action == "update_notes")
        )).scalar_one()
    assert change.old_value == "old note" and change.new_value == "Received 20 Nov 2026 by FAST"
    assert audit.output_json["previous_notes"] == "old note"

    missing = await client.patch(f"/api/payments/{uuid.uuid4()}/notes", json={"notes": "x"}, headers=auth_headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_pdf_for_paid_invoice_keeps_previous_file(client: AsyncClient, auth_headers: dict):
    resp = await client.post(f"/api/invoices/{ids['inv']}/regenerate-pdf", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    new_pdf = await _pdf_file_id(ids["inv"])
    assert new_pdf != "None" and new_pdf != ids["issued_pdf"]

    async with TestSessionLocal() as session:
        log = (await session.execute(
            select(AuditLog)
            .where(AuditLog.entity_id == uuid.UUID(ids["inv"]), AuditLog.action == "regenerate_pdf")
        )).scalar_one()
    assert log.input_json["previous_pdf_file_id"] == ids["issued_pdf"]
    assert log.output_json == {"issued_pdf_file_id": new_pdf, "status": "paid"}
