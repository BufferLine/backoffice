import pytest
from httpx import AsyncClient

from app.config import Settings
from app.services.file_storage import build_content_disposition, safe_filename


@pytest.mark.asyncio
async def test_health_response_sets_security_headers(client: AsyncClient):
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["Permissions-Policy"].startswith("accelerometer=()")
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert resp.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]


@pytest.mark.asyncio
async def test_cors_allows_only_configured_origins(client: AsyncClient):
    allowed = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = await client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "Access-Control-Allow-Credentials" in allowed.headers
    assert blocked.status_code == 400
    assert "Access-Control-Allow-Origin" not in blocked.headers


def test_content_disposition_blocks_header_injection():
    header = build_content_disposition('report\r\nX-Injected: bad".csv')
    assert "\r" not in header
    assert "\n" not in header
    assert 'filename="reportX-Injected_ bad_.csv"' in header
    assert "filename*=UTF-8''reportX-Injected%3A%20bad%22.csv" in header


def test_safe_filename_and_content_disposition_preserve_safe_fallbacks():
    assert safe_filename("../../ payroll \n.csv") == "_.._ payroll .csv"
    header = build_content_disposition("salary report 2026.csv")
    assert header == (
        'attachment; filename="salary report 2026.csv"; '
        "filename*=UTF-8''salary%20report%202026.csv"
    )


def test_settings_trim_empty_cors_origins():
    settings = Settings(CORS_ORIGINS=" http://localhost:3000, ,https://admin.example.com  ")
    assert settings.cors_origins_list == ["http://localhost:3000", "https://admin.example.com"]
