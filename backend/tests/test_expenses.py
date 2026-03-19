"""
E2E integration tests for the expense lifecycle.
"""

import pytest
from httpx import AsyncClient

_expense_id: str = ""


@pytest.mark.asyncio
async def test_create_expense(client: AsyncClient, auth_headers: dict):
    global _expense_id
    resp = await client.post(
        "/api/expenses",
        json={
            "expense_date": "2026-03-15",
            "vendor": "AWS",
            "category": "software",
            "currency": "USD",
            "amount": "299.00",
            "payment_method": "company_card",
            "reimbursable": False,
            "notes": "Cloud hosting March 2026",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create expense failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "draft"
    assert body["vendor"] == "AWS"
    assert body["category"] == "software"
    assert float(body["amount"]) == 299.0
    assert body["reimbursable"] is False
    _expense_id = body["id"]


@pytest.mark.asyncio
async def test_get_expense(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/expenses/{_expense_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == _expense_id


@pytest.mark.asyncio
async def test_update_expense(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/expenses/{_expense_id}",
        json={"notes": "Cloud hosting March 2026 - updated", "amount": "310.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Update expense failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["notes"] == "Cloud hosting March 2026 - updated"
    assert float(body["amount"]) == 310.0


@pytest.mark.asyncio
async def test_list_expenses(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/expenses", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_list_expenses_filter_by_category(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/expenses?category=software", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["category"] == "software"


@pytest.mark.asyncio
async def test_confirm_expense(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/expenses/{_expense_id}/confirm",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Confirm expense failed: {resp.status_code}: {resp.text}"
    assert resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_confirm_expense_again_is_409(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/expenses/{_expense_id}/confirm",
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 confirming twice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_cannot_update_confirmed_expense(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/expenses/{_expense_id}",
        json={"notes": "Should not update"},
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 updating confirmed expense, got {resp.status_code}"


@pytest.mark.asyncio
async def test_create_reimbursable_expense(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/expenses",
        json={
            "expense_date": "2026-03-10",
            "vendor": "Grab",
            "category": "transport",
            "currency": "SGD",
            "amount": "45.00",
            "reimbursable": True,
            "notes": "Client meeting transport",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["reimbursable"] is True
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_expense_not_found(client: AsyncClient, auth_headers: dict):
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/expenses/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_expenses_filter_by_status(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/expenses?expense_status=confirmed", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["status"] == "confirmed"
