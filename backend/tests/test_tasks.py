"""
E2E integration tests for the task/todo system.
"""

import pytest
from httpx import AsyncClient

_template_id: str = ""
_instance_id: str = ""
_adhoc_id: str = ""


@pytest.mark.asyncio
async def test_list_templates_includes_system_seeds(client: AsyncClient, auth_headers: dict):
    """System templates are seeded at startup via seed_compliance_tasks."""
    # Seed manually since lifespan is disabled in tests
    from app.database import Base
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.conftest import TestSessionLocal
    from app.services.task import seed_compliance_tasks

    async with TestSessionLocal() as session:
        await seed_compliance_tasks(session)
        await session.commit()

    resp = await client.get("/api/tasks/templates", headers=auth_headers)
    assert resp.status_code == 200, f"List templates failed: {resp.text}"
    body = resp.json()
    assert isinstance(body, list)
    titles = [t["title"] for t in body]
    assert "CPF Payment" in titles
    assert "Run Payroll" in titles


@pytest.mark.asyncio
async def test_create_template(client: AsyncClient, auth_headers: dict):
    global _template_id
    resp = await client.post(
        "/api/tasks/templates",
        json={
            "title": "Test Monthly Task",
            "description": "A test monthly recurring task",
            "category": "operations",
            "frequency": "monthly",
            "due_day": 15,
            "priority": "medium",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create template failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["title"] == "Test Monthly Task"
    assert body["frequency"] == "monthly"
    assert body["due_day"] == 15
    assert body["is_system"] is False
    assert body["is_active"] is True
    _template_id = body["id"]


@pytest.mark.asyncio
async def test_get_template(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/tasks/templates/{_template_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == _template_id


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/tasks/templates/{_template_id}",
        json={"priority": "high", "due_day": 20},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Update template failed: {resp.text}"
    body = resp.json()
    assert body["priority"] == "high"
    assert body["due_day"] == 20


@pytest.mark.asyncio
async def test_create_adhoc_instance(client: AsyncClient, auth_headers: dict):
    global _adhoc_id
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Ad-hoc compliance review",
            "description": "One-off review task",
            "category": "compliance",
            "priority": "high",
            "period": "2026-03",
            "due_date": "2026-03-31",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create instance failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["title"] == "Ad-hoc compliance review"
    assert body["status"] == "pending"
    assert body["category"] == "compliance"
    assert body["template_id"] is None
    _adhoc_id = body["id"]


@pytest.mark.asyncio
async def test_get_instance(client: AsyncClient, auth_headers: dict):
    resp = await client.get(f"/api/tasks/{_adhoc_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == _adhoc_id


@pytest.mark.asyncio
async def test_list_instances(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/tasks", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_list_instances_filter_by_period(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/tasks?period=2026-03", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        assert item["period"] == "2026-03"


@pytest.mark.asyncio
async def test_update_instance_status(client: AsyncClient, auth_headers: dict):
    resp = await client.patch(
        f"/api/tasks/{_adhoc_id}",
        json={"status": "in_progress", "notes": "Working on it"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Update instance failed: {resp.text}"
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["notes"] == "Working on it"


@pytest.mark.asyncio
async def test_complete_instance(client: AsyncClient, auth_headers: dict):
    global _instance_id
    # Create a fresh instance to complete
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Task to complete",
            "category": "operations",
            "priority": "low",
            "period": "2026-03",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    _instance_id = resp.json()["id"]

    resp = await client.post(
        f"/api/tasks/{_instance_id}/complete",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Complete failed: {resp.text}"
    body = resp.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None
    assert body["completed_by"] is not None


@pytest.mark.asyncio
async def test_skip_instance(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Task to skip",
            "category": "operations",
            "priority": "low",
            "period": "2026-03",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    skip_id = resp.json()["id"]

    resp = await client.post(
        f"/api/tasks/{skip_id}/skip",
        params={"notes": "Not applicable this month"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Skip failed: {resp.text}"
    body = resp.json()
    assert body["status"] == "skipped"
    assert "Not applicable" in (body["notes"] or "")


@pytest.mark.asyncio
async def test_generate_instances_for_month(client: AsyncClient, auth_headers: dict):
    """Trigger via automation endpoint or service directly."""
    from tests.conftest import TestSessionLocal
    from app.services.task import generate_instances_for_month

    async with TestSessionLocal() as session:
        created = await generate_instances_for_month(session, "2026-04")
        await session.commit()

    assert isinstance(created, list)
    # Should have created monthly templates at minimum
    assert len(created) >= 1


@pytest.mark.asyncio
async def test_generate_instances_idempotent(client: AsyncClient, auth_headers: dict):
    """Running generate twice for same month creates no duplicates."""
    from tests.conftest import TestSessionLocal
    from app.services.task import generate_instances_for_month

    async with TestSessionLocal() as session:
        first_run = await generate_instances_for_month(session, "2026-05")
        await session.commit()

    async with TestSessionLocal() as session:
        second_run = await generate_instances_for_month(session, "2026-05")
        await session.commit()

    # Second run should create 0 new instances
    assert len(second_run) == 0


@pytest.mark.asyncio
async def test_todo_summary(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/tasks/todo/2026-03", headers=auth_headers)
    assert resp.status_code == 200, f"Todo summary failed: {resp.text}"
    body = resp.json()
    assert body["period"] == "2026-03"
    assert "pending" in body
    assert "in_progress" in body
    assert "completed" in body
    assert "overdue" in body
    assert "items" in body
    # We created tasks above in 2026-03
    assert body["completed"] >= 1


@pytest.mark.asyncio
async def test_upcoming_tasks(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/tasks/upcoming?days=60", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_overdue_tasks(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/tasks/overdue", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_instance_not_found(client: AsyncClient, auth_headers: dict):
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/tasks/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_template_not_found(client: AsyncClient, auth_headers: dict):
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/tasks/templates/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_template(client: AsyncClient, auth_headers: dict):
    """Soft-delete a user-created template (is_active=False)."""
    resp = await client.delete(f"/api/tasks/templates/{_template_id}", headers=auth_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_system_template(client: AsyncClient, auth_headers: dict):
    """System templates cannot be deleted."""
    # Get a system template id
    resp = await client.get("/api/tasks/templates", headers=auth_headers)
    assert resp.status_code == 200
    system_templates = [t for t in resp.json() if t["is_system"]]
    assert len(system_templates) > 0, "No system templates found"
    system_id = system_templates[0]["id"]

    resp = await client.delete(f"/api/tasks/templates/{system_id}", headers=auth_headers)
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
