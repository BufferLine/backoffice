"""
E2E integration tests for the full invoice lifecycle.
Tests are ordered and share session-scoped state via module-level variables.
"""

import pytest
from httpx import AsyncClient

# Module-level state shared across tests in order
_client_id: str = ""
_invoice_id: str = ""
_line_item_id: str = ""
_payment_id: str = ""
_invoice_id_for_cancel: str = ""


@pytest.mark.asyncio
async def test_create_client(client: AsyncClient, auth_headers: dict):
    global _client_id
    resp = await client.post(
        "/api/clients",
        json={
            "legal_name": "Acme Corp Pte Ltd",
            "billing_email": "billing@acme.com",
            "billing_address": "100 Acme Road, Singapore 400100",
            "default_currency": "SGD",
            "payment_terms_days": 30,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create client failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["legal_name"] == "Acme Corp Pte Ltd"
    assert body["is_active"] is True
    _client_id = body["id"]


@pytest.mark.asyncio
async def test_list_clients(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/clients", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(c["id"] == _client_id for c in body), "Created client not in list"


@pytest.mark.asyncio
async def test_get_client(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/clients/{_client_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == _client_id


@pytest.mark.asyncio
async def test_create_invoice_draft(client: AsyncClient, auth_headers: dict):
    global _invoice_id
    resp = await client.post(
        "/api/invoices",
        json={
            "client_id": _client_id,
            "currency": "SGD",
            "description": "Consulting services Q1 2026",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create invoice failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "draft"
    assert body["client_id"] == _client_id
    assert body["currency"] == "SGD"
    assert body["invoice_number"].startswith("INV-")
    assert body["line_items"] == []
    _invoice_id = body["id"]


@pytest.mark.asyncio
async def test_update_draft_invoice(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/invoices/{_invoice_id}",
        json={"description": "Consulting services Q1 2026 - Updated"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Update invoice failed: {resp.status_code}: {resp.text}"
    assert resp.json()["description"] == "Consulting services Q1 2026 - Updated"


@pytest.mark.asyncio
async def test_add_line_item(client: AsyncClient, auth_headers: dict):
    global _line_item_id
    resp = await client.post(
        f"/api/invoices/{_invoice_id}/line-items",
        json={
            "description": "Backend development - 40 hours",
            "quantity": "40",
            "unit_price": "150.00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Add line item failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["description"] == "Backend development - 40 hours"
    assert float(body["quantity"]) == 40.0
    assert float(body["unit_price"]) == 150.0
    assert float(body["amount"]) == 6000.0
    _line_item_id = body["id"]


@pytest.mark.asyncio
async def test_get_invoice_with_line_item(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/invoices/{_invoice_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["line_items"]) == 1, "Invoice should have 1 line item"
    assert body["line_items"][0]["id"] == _line_item_id
    # Totals should be recalculated
    assert float(body["subtotal_amount"]) == 6000.0
    assert float(body["total_amount"]) >= 6000.0


@pytest.mark.asyncio
async def test_add_second_line_item(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/invoices/{_invoice_id}/line-items",
        json={
            "description": "DevOps setup",
            "quantity": "1",
            "unit_price": "500.00",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_invoice_totals_after_two_items(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/invoices/{_invoice_id}", headers=auth_headers)
    body = resp.json()
    assert len(body["line_items"]) == 2
    assert float(body["subtotal_amount"]) == 6500.0


@pytest.mark.asyncio
async def test_issue_invoice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/invoices/{_invoice_id}/issue",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Issue invoice failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "issued"
    assert body["invoice_number"].startswith("INV-")
    assert body["issue_date"] is not None
    assert body["due_date"] is not None


@pytest.mark.asyncio
async def test_issue_same_invoice_idempotent(client: AsyncClient, auth_headers: dict):
    """Issuing an already-issued invoice should succeed (idempotent)."""
    resp = await client.post(
        f"/api/invoices/{_invoice_id}/issue",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Idempotent issue failed: {resp.status_code}: {resp.text}"
    assert resp.json()["status"] == "issued"


@pytest.mark.asyncio
async def test_cannot_update_issued_invoice(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/invoices/{_invoice_id}",
        json={"description": "Should not work"},
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 updating issued invoice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_cannot_add_line_item_to_issued_invoice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/invoices/{_invoice_id}/line-items",
        json={"description": "Extra", "quantity": "1", "unit_price": "100"},
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 adding line item to issued invoice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_record_payment_for_invoice(client: AsyncClient, auth_headers: dict):
    global _payment_id
    # Get the invoice total first
    inv_resp = await client.get(f"/api/invoices/{_invoice_id}", headers=auth_headers)
    total = inv_resp.json()["total_amount"]

    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer",
            "currency": "SGD",
            "amount": str(total),
            "payment_date": "2026-03-19",
            "bank_reference": "REF-001",
            "notes": "Full payment for invoice",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Record payment failed: {resp.status_code}: {resp.text}"
    _payment_id = resp.json()["id"]


@pytest.mark.asyncio
async def test_link_payment_to_invoice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payments/{_payment_id}/link",
        json={
            "related_entity_type": "invoice",
            "related_entity_id": _invoice_id,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Link payment failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["related_entity_type"] == "invoice"
    assert body["related_entity_id"] == _invoice_id


@pytest.mark.asyncio
async def test_invoice_is_now_paid(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/invoices/{_invoice_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid", "Invoice should be paid after linking payment"


@pytest.mark.asyncio
async def test_cancel_invoice_no_payments(client: AsyncClient, auth_headers: dict):
    global _invoice_id_for_cancel
    # Create a fresh invoice to cancel
    create_resp = await client.post(
        "/api/invoices",
        json={"client_id": _client_id, "currency": "SGD", "description": "To be cancelled"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]
    _invoice_id_for_cancel = inv_id

    # Add a line item and issue it
    await client.post(
        f"/api/invoices/{inv_id}/line-items",
        json={"description": "Item", "quantity": "1", "unit_price": "100"},
        headers=auth_headers,
    )
    await client.post(f"/api/invoices/{inv_id}/issue", headers=auth_headers)

    # Now cancel it
    resp = await client.post(f"/api/invoices/{inv_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200, f"Cancel failed: {resp.status_code}: {resp.text}"
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_issue_cancelled_invoice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/invoices/{_invoice_id_for_cancel}/issue",
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 issuing cancelled invoice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_list_invoices(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/invoices", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 2


@pytest.mark.asyncio
async def test_list_invoices_filter_by_status(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/invoices?invoice_status=paid", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["status"] == "paid"


@pytest.mark.asyncio
async def test_cannot_issue_invoice_without_line_items(client: AsyncClient, auth_headers: dict):
    # Create invoice with no line items
    create_resp = await client.post(
        "/api/invoices",
        json={"client_id": _client_id, "currency": "SGD"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    empty_inv_id = create_resp.json()["id"]

    # Try to issue it (should fail - no line items)
    resp = await client.post(f"/api/invoices/{empty_inv_id}/issue", headers=auth_headers)
    assert resp.status_code == 422, f"Expected 422 issuing invoice without line items, got {resp.status_code}"
