"""
E2E integration tests for auth endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_valid_credentials(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "access_token" in body, "access_token missing from login response"
    assert "refresh_token" in body, "refresh_token missing from login response"
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401, f"Expected 401 for wrong password, got {resp.status_code}"


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@test.com", "password": "testpass123"},
    )
    assert resp.status_code == 401, f"Expected 401 for unknown email, got {resp.status_code}"


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200, f"Expected 200 for /me, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["email"] == "admin@test.com"
    assert body["is_active"] is True
    assert len(body["roles"]) > 0, "Superadmin should have at least one role"
    assert len(body["permissions"]) > 0, "Superadmin should have permissions"
    # Superadmin should have all permissions
    perms = set(body["permissions"])
    assert "invoice:read" in perms
    assert "payroll:finalize" in perms
    assert "admin:manage_users" in perms


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"


@pytest.mark.asyncio
async def test_me_with_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"},
    )
    assert resp.status_code == 401, f"Expected 401 with invalid token, got {resp.status_code}"


@pytest.mark.asyncio
async def test_create_api_token(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/auth/api-tokens",
        json={"name": "test-cli-token"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Expected 201 for api-token creation, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "token" in body, "Raw token should be returned once on creation"
    assert body["name"] == "test-cli-token"
    assert "id" in body


@pytest.mark.asyncio
async def test_api_token_can_authenticate(client: AsyncClient, auth_headers: dict):
    # Create a token
    create_resp = await client.post(
        "/api/auth/api-tokens",
        json={"name": "auth-check-token"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    raw_token = create_resp.json()["token"]

    # Use the raw token to call /me
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert resp.status_code == 200, f"API token auth failed: {resp.status_code}: {resp.text}"
    assert resp.json()["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    # First login to get tokens
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "testpass123"},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Use refresh token to get new access token
    resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200, f"Refresh failed: {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client: AsyncClient):
    resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401, f"Expected 401 for invalid refresh token, got {resp.status_code}"


@pytest.mark.asyncio
async def test_refresh_missing_token(client: AsyncClient):
    resp = await client.post("/api/auth/refresh", json={})
    assert resp.status_code == 422, f"Expected 422 for missing refresh_token, got {resp.status_code}"
