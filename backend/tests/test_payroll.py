"""
E2E integration tests for the full payroll lifecycle.

Proration check (for SG jurisdiction):
  - Employee base salary: SGD 9,200/month
  - Month: 2026-03 (31 days)
  - start_date: 2026-03-19 → days_worked = 31 - 19 + 1 = 13
  - prorated_gross = 9200 * 13 / 31 ≈ 3,858.06

SDL deduction (Skills Development Levy, SG):
  - Rate: 0.25% of prorated gross, capped at SGD 11.25/month
  - SDL = 3858.06 * 0.0025 ≈ 9.65 (below cap)
"""

import pytest
from decimal import Decimal
from httpx import AsyncClient

_employee_id: str = ""
_payroll_run_id: str = ""
_payment_id: str = ""


@pytest.mark.asyncio
async def test_create_employee(client: AsyncClient, auth_headers: dict):
    global _employee_id
    resp = await client.post(
        "/api/employees",
        json={
            "name": "Jane Doe",
            "email": "jane.doe@test.com",
            "base_salary": "9200.00",
            "salary_currency": "SGD",
            "start_date": "2026-01-01",
            "work_pass_type": "EP",
            "tax_residency": "resident",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create employee failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["name"] == "Jane Doe"
    assert body["status"] == "active"
    assert float(body["base_salary"]) == 9200.0
    _employee_id = body["id"]


@pytest.mark.asyncio
async def test_list_employees(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/employees", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(e["id"] == _employee_id for e in body)


@pytest.mark.asyncio
async def test_get_employee(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/employees/{_employee_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == _employee_id


@pytest.mark.asyncio
async def test_create_payroll_run(client: AsyncClient, auth_headers: dict):
    global _payroll_run_id
    resp = await client.post(
        "/api/payroll/runs",
        json={
            "employee_id": _employee_id,
            "month": "2026-03",
            "start_date": "2026-03-19",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create payroll run failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "draft"
    assert body["employee_id"] == _employee_id
    assert body["employee_name"] == "Jane Doe"
    assert body["days_in_month"] == 31
    assert body["days_worked"] == 13, f"Expected 13 days worked (Mar 19-31), got {body['days_worked']}"
    _payroll_run_id = body["id"]


@pytest.mark.asyncio
async def test_payroll_proration(client: AsyncClient, auth_headers: dict):
    """Verify prorated gross salary calculation."""
    resp = await client.get(f"/api/payroll/runs/{_payroll_run_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    # 9200 * 13 / 31 = 3858.064516...
    prorated = Decimal(body["prorated_gross_salary"])
    expected = Decimal("9200") * Decimal("13") / Decimal("31")
    # Allow 1 cent tolerance for rounding
    assert abs(prorated - expected) < Decimal("0.02"), (
        f"Prorated gross {prorated} doesn't match expected ~{expected:.2f}"
    )


@pytest.mark.asyncio
async def test_payroll_sdl_deduction_exists(client: AsyncClient, auth_headers: dict):
    """Verify SDL deduction is present in the payroll run (as employer cost)."""
    resp = await client.get(f"/api/payroll/runs/{_payroll_run_id}", headers=auth_headers)
    body = resp.json()
    # SDL is an employer cost, not an employee deduction
    employer_costs = body.get("employer_costs", [])
    assert len(employer_costs) > 0, "Payroll run should have employer costs"

    cost_types = [d["deduction_type"] for d in employer_costs]
    assert "sdl" in cost_types, f"SDL not found in employer costs. Types: {cost_types}"

    sdl = next(d for d in employer_costs if d["deduction_type"] == "sdl")
    sdl_amount = Decimal(sdl["amount"])
    # SDL = 0.25% of prorated_gross, capped at 11.25
    prorated = Decimal("9200") * Decimal("13") / Decimal("31")
    expected_sdl = min(prorated * Decimal("0.0025"), Decimal("11.25"))
    assert abs(sdl_amount - expected_sdl) < Decimal("0.02"), (
        f"SDL amount {sdl_amount} doesn't match expected ~{expected_sdl:.2f}"
    )


@pytest.mark.asyncio
async def test_payroll_no_cpf_for_ep_holder(client: AsyncClient, auth_headers: dict):
    """EP holders should not have CPF deductions (only citizens/PRs get CPF)."""
    resp = await client.get(f"/api/payroll/runs/{_payroll_run_id}", headers=auth_headers)
    body = resp.json()
    all_types = [d["deduction_type"] for d in body.get("deductions", [])]
    all_types += [d["deduction_type"] for d in body.get("employer_costs", [])]
    assert "cpf_employee" not in all_types, "EP holder should not have CPF employee deduction"
    assert "cpf_employer" not in all_types, "EP holder should not have CPF employer cost"


@pytest.mark.asyncio
async def test_payroll_deductions_have_required_fields(client: AsyncClient, auth_headers: dict):
    """All deductions/employer_costs should have required fields populated."""
    resp = await client.get(f"/api/payroll/runs/{_payroll_run_id}", headers=auth_headers)
    body = resp.json()
    for d in body.get("employer_costs", []) + body.get("deductions", []):
        assert "deduction_type" in d, "Missing deduction_type"
        assert "amount" in d, "Missing amount"
        assert "description" in d, "Missing description"
        assert float(d["amount"]) >= 0, f"Negative deduction amount: {d['amount']}"


@pytest.mark.asyncio
async def test_payroll_net_salary_equals_gross_minus_deductions(client: AsyncClient, auth_headers: dict):
    """Net salary = prorated gross - employee deductions (not employer costs)."""
    resp = await client.get(f"/api/payroll/runs/{_payroll_run_id}", headers=auth_headers)
    body = resp.json()
    gross = Decimal(body["prorated_gross_salary"])
    net = Decimal(body["net_salary"])
    total_deductions = Decimal(body["total_deductions"])
    # EP holder: no employee deductions, so net == gross
    assert total_deductions == Decimal("0"), f"EP holder should have 0 employee deductions, got {total_deductions}"
    assert net == gross, f"Net {net} should equal gross {gross} for EP holder with no employee deductions"


@pytest.mark.asyncio
async def test_review_payroll_run(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payroll/runs/{_payroll_run_id}/review",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Review payroll failed: {resp.status_code}: {resp.text}"
    assert resp.json()["status"] == "reviewed"


@pytest.mark.asyncio
async def test_cannot_review_twice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payroll/runs/{_payroll_run_id}/review",
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 reviewing twice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_finalize_payroll_run(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payroll/runs/{_payroll_run_id}/finalize",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Finalize payroll failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "finalized"


@pytest.mark.asyncio
async def test_cannot_finalize_twice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payroll/runs/{_payroll_run_id}/finalize",
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 finalizing twice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_record_payment_for_payroll(client: AsyncClient, auth_headers: dict):
    global _payment_id
    # Get the net salary
    run_resp = await client.get(f"/api/payroll/runs/{_payroll_run_id}", headers=auth_headers)
    net = run_resp.json()["net_salary"]

    resp = await client.post(
        "/api/payments",
        json={
            "payment_type": "bank_transfer",
            "currency": "SGD",
            "amount": str(net),
            "payment_date": "2026-03-31",
            "bank_reference": "PAYROLL-2026-03",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Record payment failed: {resp.status_code}: {resp.text}"
    _payment_id = resp.json()["id"]


@pytest.mark.asyncio
async def test_mark_payroll_paid(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payroll/runs/{_payroll_run_id}/mark-paid",
        json={"payment_id": _payment_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Mark payroll paid failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "paid"
    assert body["payment_id"] == _payment_id
    assert body["paid_at"] is not None


@pytest.mark.asyncio
async def test_cannot_mark_paid_twice(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"/api/payroll/runs/{_payroll_run_id}/mark-paid",
        json={"payment_id": _payment_id},
        headers=auth_headers,
    )
    assert resp.status_code == 409, f"Expected 409 marking paid twice, got {resp.status_code}"


@pytest.mark.asyncio
async def test_list_payroll_runs(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/payroll/runs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_list_payroll_runs_filter_by_month(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/payroll/runs?month=2026-03", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["month"].startswith("2026-03"), f"Month mismatch: {item['month']}"


@pytest.mark.asyncio
async def test_cannot_create_payroll_for_inactive_employee(client: AsyncClient, auth_headers: dict):
    # Deactivate the employee first
    await client.patch(
        f"/api/employees/{_employee_id}",
        json={"status": "terminated"},
        headers=auth_headers,
    )
    resp = await client.post(
        "/api/payroll/runs",
        json={
            "employee_id": _employee_id,
            "month": "2026-04",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422, f"Expected 422 for inactive employee, got {resp.status_code}"
