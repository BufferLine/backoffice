"""
E2E integration tests for account balance and transaction tracking.

Account balance is derived from confirmed journal lines (double-entry), not
from the legacy ``transactions`` table — see ``services.account.get_balance``.
Balance tests therefore post journal entries against the bank account; the
transaction tests only cover the legacy transaction lifecycle.
"""

import pytest
from httpx import AsyncClient

_account_id: str = ""
_tx_inflow_id: str = ""
_tx_outflow_id: str = ""
_commitment_id: str = ""
_revenue_account_id: str = ""
_expense_account_id: str = ""


async def _post_journal_entry(
    client: AsyncClient,
    auth_headers: dict,
    *,
    debit_account: str,
    credit_account: str,
    amount: str,
    entry_date: str,
    is_confirmed: bool,
) -> str:
    resp = await client.post(
        "/api/journal-entries",
        json={
            "entry_date": entry_date,
            "is_confirmed": is_confirmed,
            "lines": [
                {"account_id": debit_account, "debit": amount, "currency": "SGD"},
                {"account_id": credit_account, "credit": amount, "currency": "SGD"},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create journal entry failed: {resp.status_code}: {resp.text}"
    return resp.json()["id"]


async def _balance(client: AsyncClient, auth_headers: dict) -> dict:
    resp = await client.get(f"/api/accounts/{_account_id}/balance", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_create_account(client: AsyncClient, auth_headers: dict):
    global _account_id
    resp = await client.post(
        "/api/accounts",
        json={
            "name": "Test Bank Account",
            "account_type": "bank",
            "account_class": "asset",
            "currency": "SGD",
            "institution": "DBS",
            "opening_balance": "1000.00",
            "opening_balance_date": "2026-01-01",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create account failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["name"] == "Test Bank Account"
    assert body["account_type"] == "bank"
    assert body["currency"] == "SGD"
    assert float(body["opening_balance"]) == 1000.0
    _account_id = body["id"]


@pytest.mark.asyncio
async def test_create_counter_accounts(client: AsyncClient, auth_headers: dict):
    """Revenue + expense accounts used as the other side of journal entries."""
    global _revenue_account_id, _expense_account_id
    for name, account_class in (("Test Revenue", "revenue"), ("Test Expense", "expense")):
        resp = await client.post(
            "/api/accounts",
            json={
                "name": name,
                "account_type": "other",
                "account_class": account_class,
                "currency": "SGD",
                "opening_balance": "0",
                "opening_balance_date": "2026-01-01",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, f"Create {name} failed: {resp.status_code}: {resp.text}"
        if account_class == "revenue":
            _revenue_account_id = resp.json()["id"]
        else:
            _expense_account_id = resp.json()["id"]


@pytest.mark.asyncio
async def test_list_accounts_with_balances(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/accounts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1
    ids = {a["id"] for a in body["items"]}
    assert _account_id in ids


@pytest.mark.asyncio
async def test_get_account(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/accounts/{_account_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == _account_id


@pytest.mark.asyncio
async def test_get_account_balance_initial(client: AsyncClient, auth_headers: dict):
    """Balance should equal opening balance before any transactions."""
    resp = await client.get(f"/api/accounts/{_account_id}/balance", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["opening_balance"]) == 1000.0
    assert float(body["confirmed_inflows"]) == 0.0
    assert float(body["confirmed_outflows"]) == 0.0
    assert float(body["current_balance"]) == 1000.0


@pytest.mark.asyncio
async def test_create_inflow_transaction(client: AsyncClient, auth_headers: dict):
    """Create a confirmed legacy inflow transaction."""
    global _tx_inflow_id
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": _account_id,
            "direction": "in",
            "amount": "500.00",
            "currency": "SGD",
            "tx_date": "2026-03-01",
            "status": "confirmed",
            "category": "invoice_payment",
            "counterparty": "Client ABC",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create inflow failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["direction"] == "in"
    assert float(body["amount"]) == 500.0
    assert body["status"] == "confirmed"
    assert body["confirmed_at"] is not None
    _tx_inflow_id = body["id"]


@pytest.mark.asyncio
async def test_create_outflow_transaction(client: AsyncClient, auth_headers: dict):
    """Create a confirmed legacy outflow transaction."""
    global _tx_outflow_id
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": _account_id,
            "direction": "out",
            "amount": "200.00",
            "currency": "SGD",
            "tx_date": "2026-03-05",
            "status": "confirmed",
            "category": "salary",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create outflow failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["direction"] == "out"
    _tx_outflow_id = body["id"]


@pytest.mark.asyncio
async def test_cancel_pending_transaction(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": _account_id,
            "direction": "in",
            "amount": "9999.00",
            "currency": "SGD",
            "tx_date": "2026-03-10",
            "status": "pending",
            "category": "other_inflow",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"
    pending_id = resp.json()["id"]

    cancel_resp = await client.post(f"/api/transactions/{pending_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_confirm_pending_transaction(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": _account_id,
            "direction": "in",
            "amount": "100.00",
            "currency": "SGD",
            "tx_date": "2026-03-15",
            "status": "pending",
            "category": "interest",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    pending_id = resp.json()["id"]

    confirm_resp = await client.post(f"/api/transactions/{pending_id}/confirm", headers=auth_headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"
    assert confirm_resp.json()["confirmed_at"] is not None


@pytest.mark.asyncio
async def test_balance_after_inflow(client: AsyncClient, auth_headers: dict):
    """Dr bank / Cr revenue 500 → balance = opening(1000) + 500 = 1500."""
    await _post_journal_entry(
        client, auth_headers,
        debit_account=_account_id, credit_account=_revenue_account_id,
        amount="500.00", entry_date="2026-03-01", is_confirmed=True,
    )
    body = await _balance(client, auth_headers)
    assert float(body["confirmed_inflows"]) == 500.0
    assert float(body["confirmed_outflows"]) == 0.0
    assert float(body["current_balance"]) == 1500.0


@pytest.mark.asyncio
async def test_balance_after_outflow(client: AsyncClient, auth_headers: dict):
    """Dr expense / Cr bank 200 → balance = 1000 + 500 - 200 = 1300."""
    await _post_journal_entry(
        client, auth_headers,
        debit_account=_expense_account_id, credit_account=_account_id,
        amount="200.00", entry_date="2026-03-05", is_confirmed=True,
    )
    body = await _balance(client, auth_headers)
    assert float(body["confirmed_outflows"]) == 200.0
    assert float(body["current_balance"]) == 1300.0


@pytest.mark.asyncio
async def test_unconfirmed_journal_entry_does_not_affect_balance(client: AsyncClient, auth_headers: dict):
    """A draft (unconfirmed) journal entry must NOT affect the balance."""
    entry_id = await _post_journal_entry(
        client, auth_headers,
        debit_account=_account_id, credit_account=_revenue_account_id,
        amount="9999.00", entry_date="2026-03-10", is_confirmed=False,
    )
    body = await _balance(client, auth_headers)
    assert float(body["current_balance"]) == 1300.0

    # Delete it so it doesn't interfere with later tests
    delete_resp = await client.delete(f"/api/journal-entries/{entry_id}", headers=auth_headers)
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_confirm_journal_entry_affects_balance(client: AsyncClient, auth_headers: dict):
    """Confirming a draft journal entry brings it into the balance."""
    entry_id = await _post_journal_entry(
        client, auth_headers,
        debit_account=_account_id, credit_account=_revenue_account_id,
        amount="100.00", entry_date="2026-03-15", is_confirmed=False,
    )
    assert float((await _balance(client, auth_headers))["current_balance"]) == 1300.0

    confirm_resp = await client.post(f"/api/journal-entries/{entry_id}/confirm", headers=auth_headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["is_confirmed"] is True

    assert float((await _balance(client, auth_headers))["current_balance"]) == 1400.0


@pytest.mark.asyncio
async def test_cancel_confirmed_transaction_raises_409(client: AsyncClient, auth_headers: dict):
    """Cannot cancel an already confirmed transaction."""
    resp = await client.post(f"/api/transactions/{_tx_inflow_id}/cancel", headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_account_transactions(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/accounts/{_account_id}/transactions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 2


@pytest.mark.asyncio
async def test_list_transactions_filter_by_status(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/transactions",
        params={"account_id": _account_id, "tx_status": "confirmed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["status"] == "confirmed"


@pytest.mark.asyncio
async def test_create_recurring_commitment(client: AsyncClient, auth_headers: dict):
    global _commitment_id
    resp = await client.post(
        "/api/recurring-commitments",
        json={
            "name": "Monthly Rent",
            "category": "rent",
            "account_id": _account_id,
            "currency": "SGD",
            "expected_amount": "3000.00",
            "frequency": "monthly",
            "day_of_period": 1,
            "vendor": "Landlord Co",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create commitment failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["name"] == "Monthly Rent"
    assert body["frequency"] == "monthly"
    _commitment_id = body["id"]


@pytest.mark.asyncio
async def test_generate_pending_transactions(client: AsyncClient, auth_headers: dict):
    """Generate pending transactions for 2026-04."""
    resp = await client.post(
        "/api/recurring-commitments/generate-pending",
        params={"month": "2026-04"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Generate pending failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["total"] >= 1
    # The generated tx should be pending
    for item in body["items"]:
        assert item["status"] == "pending"
        assert item["recurring_commitment_id"] == _commitment_id


@pytest.mark.asyncio
async def test_generate_pending_idempotent(client: AsyncClient, auth_headers: dict):
    """Generating twice for the same month should not create duplicates."""
    resp1 = await client.post(
        "/api/recurring-commitments/generate-pending",
        params={"month": "2026-05"},
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    count1 = resp1.json()["total"]

    resp2 = await client.post(
        "/api/recurring-commitments/generate-pending",
        params={"month": "2026-05"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    count2 = resp2.json()["total"]

    # Second call should generate 0 new transactions
    assert count2 == 0, f"Expected 0 on second call, got {count2}"


@pytest.mark.asyncio
async def test_confirm_commitment_transaction(client: AsyncClient, auth_headers: dict):
    """Confirm the pending transaction generated by the recurring commitment."""
    txs_resp = await client.get(
        f"/api/accounts/{_account_id}/transactions",
        params={"tx_status": "pending"},
        headers=auth_headers,
    )
    pending_txs = [t for t in txs_resp.json()["items"] if t["recurring_commitment_id"] == _commitment_id]
    assert len(pending_txs) >= 1
    tx_id = pending_txs[0]["id"]
    assert pending_txs[0]["direction"] == "out"
    assert float(pending_txs[0]["amount"]) == 3000.0

    confirm_resp = await client.post(f"/api/transactions/{tx_id}/confirm", headers=auth_headers)
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_rent_journal_entry_affects_balance(client: AsyncClient, auth_headers: dict):
    """Booking the rent (Dr expense / Cr bank 3000) decreases the balance by 3000."""
    balance_before = float((await _balance(client, auth_headers))["current_balance"])
    await _post_journal_entry(
        client, auth_headers,
        debit_account=_expense_account_id, credit_account=_account_id,
        amount="3000.00", entry_date="2026-04-01", is_confirmed=True,
    )
    balance_after = float((await _balance(client, auth_headers))["current_balance"])
    assert balance_after == pytest.approx(balance_before - 3000.0, abs=0.01)


@pytest.mark.asyncio
async def test_deactivate_commitment(client: AsyncClient, auth_headers: dict):
    resp = await client.delete(f"/api/recurring-commitments/{_commitment_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False


@pytest.mark.asyncio
async def test_balance_formula(client: AsyncClient, auth_headers: dict):
    """Verify: balance = opening_balance + confirmed_in - confirmed_out."""
    balance_resp = await client.get(f"/api/accounts/{_account_id}/balance", headers=auth_headers)
    body = balance_resp.json()
    opening = float(body["opening_balance"])
    inflows = float(body["confirmed_inflows"])
    outflows = float(body["confirmed_outflows"])
    current = float(body["current_balance"])
    assert current == pytest.approx(opening + inflows - outflows, abs=0.01)
