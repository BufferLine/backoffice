"""
E2E integration tests for payment recording and linking.
"""

import pytest
import uuid
from httpx import AsyncClient

_bank_payment_id: str = ""
_crypto_payment_id: str = ""
_crypto_tx_hash: str = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab"


@pytest.mark.asyncio
async def test_record_bank_payment(client: AsyncClient, auth_headers: dict):
    global _bank_payment_id
    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer",
            "currency": "SGD",
            "amount": "1000.00",
            "payment_date": "2026-03-19",
            "bank_reference": "BANK-REF-001",
            "notes": "Bank payment test",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Record bank payment failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["payment_type"] == "bank_transfer"
    assert float(body["amount"]) == 1000.0
    assert body["currency"] == "SGD"
    assert body["bank_reference"] == "BANK-REF-001"
    assert body["tx_hash"] is None
    _bank_payment_id = body["id"]


@pytest.mark.asyncio
async def test_record_crypto_payment(client: AsyncClient, auth_headers: dict):
    global _crypto_payment_id
    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "crypto",
            "currency": "USDC",
            "amount": "5000.00",
            "payment_date": "2026-03-19",
            "tx_hash": _crypto_tx_hash,
            "chain_id": "ethereum",
            "fx_rate_to_sgd": "1.35",
            "fx_rate_date": "2026-03-19",
            "fx_rate_source": "manual",
            "notes": "Crypto payment test",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Record crypto payment failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["payment_type"] == "crypto"
    assert body["tx_hash"] == _crypto_tx_hash
    assert body["chain_id"] == "ethereum"
    assert float(body["fx_rate_to_sgd"]) == 1.35
    # SGD value should be computed: 5000 * 1.35 = 6750
    assert float(body["sgd_value"]) == pytest.approx(6750.0, abs=0.01)
    _crypto_payment_id = body["id"]


@pytest.mark.asyncio
async def test_duplicate_tx_hash_is_409(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "crypto",
            "currency": "USDC",
            "amount": "100.00",
            "tx_hash": _crypto_tx_hash,  # same tx_hash as above
            "chain_id": "ethereum",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 for duplicate tx_hash, got {resp.status_code}"


@pytest.mark.asyncio
async def test_get_payment(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/payments/{_bank_payment_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == _bank_payment_id
    assert body["payment_type"] == "bank_transfer"


@pytest.mark.asyncio
async def test_list_payments(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/payments", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 2

    payment_ids = {p["id"] for p in body["items"]}
    assert _bank_payment_id in payment_ids
    assert _crypto_payment_id in payment_ids


@pytest.mark.asyncio
async def test_payment_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/payments/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_idempotency_key(client: AsyncClient, auth_headers: dict):
    """Same idempotency_key should return the same payment without error."""
    key = f"idem-key-{uuid.uuid4()}"
    payload = {
        "payment_type": "bank_transfer",
        "currency": "SGD",
        "amount": "250.00",
        "idempotency_key": key,
    }
    resp1 = await client.post("/api/payments", json=payload, headers=auth_headers)
    assert resp1.status_code == 201
    id1 = resp1.json()["id"]

    resp2 = await client.post("/api/payments", json=payload, headers=auth_headers)
    assert resp2.status_code == 201
    id2 = resp2.json()["id"]

    assert id1 == id2, "Idempotency key should return the same payment record"


@pytest.mark.asyncio
async def test_link_payment_to_invoice(client: AsyncClient, auth_headers: dict):
    """
    Full flow: create client → invoice → line item → issue → payment → link.
    Verifies the link endpoint works correctly.
    """
    # Create a client
    client_resp = await client.post(
        "/api/clients",
        json={"legal_name": "Payment Test Client", "default_currency": "SGD"},
        headers=auth_headers,
    )
    assert client_resp.status_code == 201
    client_id = client_resp.json()["id"]

    # Create invoice
    inv_resp = await client.post(
        "/api/invoices",
        json={"client_id": client_id, "currency": "SGD"},
        headers=auth_headers,
    )
    assert inv_resp.status_code == 201
    invoice_id = inv_resp.json()["id"]

    # Add line item
    await client.post(
        f"/api/invoices/{invoice_id}/line-items",
        json={"description": "Service", "quantity": "1", "unit_price": "500.00"},
        headers=auth_headers,
    )

    # Issue invoice
    issue_resp = await client.post(f"/api/invoices/{invoice_id}/issue", headers=auth_headers)
    assert issue_resp.status_code == 200
    total = issue_resp.json()["total_amount"]

    # Record a matching payment
    pay_resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer",
            "currency": "SGD",
            "amount": str(total),
            "payment_date": "2026-03-19",
        },
        headers=auth_headers,
    )
    assert pay_resp.status_code == 201
    payment_id = pay_resp.json()["id"]

    # Link payment to invoice
    link_resp = await client.post(
        f"/api/payments/{payment_id}/link",
        json={"related_entity_type": "invoice", "related_entity_id": invoice_id},
        headers=auth_headers,
    )
    assert link_resp.status_code == 200, f"Link failed: {link_resp.status_code}: {link_resp.text}"
    body = link_resp.json()
    assert body["related_entity_type"] == "invoice"
    assert body["related_entity_id"] == invoice_id

    # Invoice should now be paid
    inv_check = await client.get(f"/api/invoices/{invoice_id}", headers=auth_headers)
    assert inv_check.json()["status"] == "paid"


@pytest.mark.asyncio
async def test_cannot_link_payment_to_draft_invoice(client: AsyncClient, auth_headers: dict):
    """Linking a payment to a draft (not issued) invoice should fail."""
    client_resp = await client.post(
        "/api/clients",
        json={"legal_name": "Draft Link Test Client"},
        headers=auth_headers,
    )
    client_id = client_resp.json()["id"]

    inv_resp = await client.post(
        "/api/invoices",
        json={"client_id": client_id, "currency": "SGD"},
        headers=auth_headers,
    )
    invoice_id = inv_resp.json()["id"]

    pay_resp = await client.post(
        "/api/payments",
        json={"payment_type": "bank_transfer", "currency": "SGD", "amount": "100.00"},
        headers=auth_headers,
    )
    payment_id = pay_resp.json()["id"]

    resp = await client.post(
        f"/api/payments/{payment_id}/link",
        json={"related_entity_type": "invoice", "related_entity_id": invoice_id},
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 linking to draft invoice, got {resp.status_code}"
