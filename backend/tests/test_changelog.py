"""
Integration tests for the universal entity change log system.

Tests:
- Employee update creates change log entries
- Invoice status change creates log
- Get entity history returns correct logs
- Get field-specific history works
- Period query works
"""

import pytest
from httpx import AsyncClient

_employee_id: str = ""
_invoice_id: str = ""
_client_id: str = ""


@pytest.mark.asyncio
async def test_create_client_for_changelog(client: AsyncClient, auth_headers: dict):
    """Create a client needed for invoice tests."""
    global _client_id
    resp = await client.post(
        "/api/clients",
        json={
            "legal_name": "Changelog Test Client",
            "billing_email": "changelog@test.com",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    _client_id = resp.json()["id"]


@pytest.mark.asyncio
async def test_create_employee_for_changelog(client: AsyncClient, auth_headers: dict):
    """Create an employee for changelog tests."""
    global _employee_id
    resp = await client.post(
        "/api/employees",
        json={
            "name": "Changelog Employee",
            "email": "changelog.emp@test.com",
            "base_salary": "5000.00",
            "salary_currency": "SGD",
            "start_date": "2026-01-01",
            "work_pass_type": "EP",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    _employee_id = resp.json()["id"]


@pytest.mark.asyncio
async def test_employee_update_creates_changelog(client: AsyncClient, auth_headers: dict):
    """PATCH /api/employees/{id} must produce change log entries."""
    resp = await client.patch(
        f"/api/employees/{_employee_id}",
        json={"base_salary": "6000.00"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    # Fetch history
    hist = await client.get(
        f"/api/changelog/employee/{_employee_id}",
        headers=auth_headers,
    )
    assert hist.status_code == 200, hist.text
    body = hist.json()
    assert body["total"] >= 1
    field_names = [item["field_name"] for item in body["items"]]
    assert "base_salary" in field_names

    # Check old/new values
    entry = next(i for i in body["items"] if i["field_name"] == "base_salary")
    assert "5000" in entry["old_value"]
    assert "6000" in entry["new_value"]


@pytest.mark.asyncio
async def test_get_field_specific_history(client: AsyncClient, auth_headers: dict):
    """GET /api/changelog/{entity_type}/{entity_id}/{field} filters by field."""
    resp = await client.get(
        f"/api/changelog/employee/{_employee_id}/base_salary",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["field_name"] == "base_salary"


@pytest.mark.asyncio
async def test_invoice_status_change_creates_changelog(client: AsyncClient, auth_headers: dict):
    """Invoice issue/cancel status transitions create change log entries."""
    global _invoice_id

    # Create invoice
    resp = await client.post(
        "/api/invoices",
        json={"client_id": _client_id, "currency": "SGD"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    _invoice_id = resp.json()["id"]

    # Add line item so it can be issued
    await client.post(
        f"/api/invoices/{_invoice_id}/line-items",
        json={"description": "Service", "quantity": 1, "unit_price": 100},
        headers=auth_headers,
    )

    # Issue the invoice
    issue_resp = await client.post(
        f"/api/invoices/{_invoice_id}/issue",
        headers=auth_headers,
    )
    assert issue_resp.status_code == 200, issue_resp.text

    # Verify change log has a status entry
    hist = await client.get(
        f"/api/changelog/invoice/{_invoice_id}",
        headers=auth_headers,
    )
    assert hist.status_code == 200, hist.text
    body = hist.json()
    assert body["total"] >= 1
    status_entries = [i for i in body["items"] if i["field_name"] == "status"]
    assert len(status_entries) >= 1
    entry = status_entries[0]
    assert entry["old_value"] == "draft"
    assert entry["new_value"] == "issued"


@pytest.mark.asyncio
async def test_period_query(client: AsyncClient, auth_headers: dict):
    """GET /api/changelog/period/{start}/{end} returns logs in range."""
    resp = await client.get(
        "/api/changelog/period/2026-01-01/2027-12-31",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1


@pytest.mark.asyncio
async def test_period_query_filtered_by_entity_type(client: AsyncClient, auth_headers: dict):
    """Period query with entity_type filter only returns matching entity types."""
    resp = await client.get(
        "/api/changelog/period/2026-01-01/2027-12-31",
        params={"entity_type": "employee"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for item in body["items"]:
        assert item["entity_type"] == "employee"


@pytest.mark.asyncio
async def test_empty_history_for_unknown_entity(client: AsyncClient, auth_headers: dict):
    """History for a non-existent entity returns empty list, not an error."""
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/changelog/employee/{fake_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
