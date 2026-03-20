import pytest
from httpx import AsyncClient

from app.services import webhook as webhook_svc


@pytest.mark.asyncio
async def test_receive_webhook_propagates_non_401_statuses(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_process_webhook(db, provider_name: str, body: bytes, headers: dict[str, str]):
        return {"error": "bad payload"}, 400

    monkeypatch.setattr(webhook_svc, "process_webhook", fake_process_webhook)

    resp = await client.post("/api/webhooks/airwallex", content=b"{}")

    assert resp.status_code == 400
    assert resp.json() == {"error": "bad payload"}


@pytest.mark.asyncio
async def test_receive_webhook_keeps_signature_failures_as_401(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_process_webhook(db, provider_name: str, body: bytes, headers: dict[str, str]):
        return {"error": "Invalid webhook signature"}, 401

    monkeypatch.setattr(webhook_svc, "process_webhook", fake_process_webhook)

    resp = await client.post("/api/webhooks/airwallex", content=b"{}")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid webhook signature"


@pytest.mark.asyncio
async def test_trigger_sync_rejects_unknown_capability(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/integrations/airwallex/sync",
        json={"capability": "invalid_capability"},
        headers=auth_headers,
    )

    assert resp.status_code == 422
