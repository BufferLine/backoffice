"""
Test configuration for E2E integration tests.

Prerequisites:
    The 'backoffice_test' PostgreSQL database must exist:
        PGPASSWORD=devpassword123 createdb -h localhost -U backoffice backoffice_test

Run:
    cd backend && source .venv/bin/activate && pytest tests/ -v
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.company import CompanySettings
from app.models.currency import Currency
from app.services.auth import create_superadmin, seed_permissions, seed_roles
from app.services.file_storage import ALLOWED_MIME_TYPES, FileStorageService, get_file_storage

TEST_DATABASE_URL = "postgresql+asyncpg://backoffice:devpassword123@localhost:5432/backoffice_test"


class MockFileStorageService(FileStorageService):
    """In-memory file storage — avoids S3/MinIO dependency in tests."""

    def __init__(self):
        # Do NOT call super().__init__() — that would connect to S3
        self._store: dict[str, bytes] = {}

    def upload(self, file_data, original_filename: str, mime_type: str) -> tuple[str, str, int]:
        import hashlib, uuid as _uuid

        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"File type '{mime_type}' is not allowed")

        content = file_data.read()
        if len(content) > settings.FILE_MAX_SIZE_BYTES:
            raise ValueError(f"File size {len(content)} exceeds maximum {settings.FILE_MAX_SIZE_BYTES}")

        sha256 = hashlib.sha256(content).hexdigest()
        storage_key = f"mock/{_uuid.uuid4()}/{original_filename}"
        self._store[storage_key] = content
        return storage_key, sha256, len(content)

    def download(self, storage_key: str) -> bytes:
        return self._store.get(storage_key, b"")

    def get_presigned_url(self, storage_key: str, expires_in: int = 3600) -> str:
        return f"http://mock-storage/{storage_key}"

    def delete(self, storage_key: str) -> None:
        self._store.pop(storage_key, None)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_size=5, max_overflow=10)


class _AutoRefreshSession(AsyncSession):
    """AsyncSession that refreshes all dirty/new objects after each flush.

    This ensures server-side onupdate values (e.g. updated_at=now()) are
    populated in-memory before pydantic serializes ORM objects inside the
    route handler — avoiding MissingGreenlet errors.
    """

    async def flush(self, objects=None):
        # Capture dirty/new before flush clears the sets
        to_refresh = list(self.dirty) + list(self.new)
        await super().flush(objects=objects)
        # Refresh to pull RETURNING / server-computed values back into __dict__
        for obj in to_refresh:
            try:
                await self.refresh(obj)
            except Exception:
                pass  # object may have been deleted or detached


TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=_AutoRefreshSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def setup_database():
    """Drop and recreate all tables once per test session, then seed base data."""
    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    # Seed base data in a fresh session (no lifespan conflicts)
    async with TestSessionLocal() as session:
        from sqlalchemy import select

        # Seed currencies required by FK constraints
        _currencies = [
            Currency(code="SGD", name="Singapore Dollar", symbol="S$", is_crypto=False, is_active=True),
            Currency(code="USD", name="US Dollar", symbol="$", is_crypto=False, is_active=True),
            Currency(code="USDC", name="USD Coin", symbol="USDC", is_crypto=True, chain_id="ethereum", is_active=True),
            Currency(code="ETH", name="Ethereum", symbol="ETH", is_crypto=True, chain_id="ethereum", is_active=True),
        ]
        for cur in _currencies:
            existing = await session.execute(select(Currency).where(Currency.code == cur.code))
            if existing.scalar_one_or_none() is None:
                session.add(cur)
        await session.flush()

        permissions_map = await seed_permissions(session)
        await seed_roles(session, permissions_map)
        await create_superadmin(session, "admin@test.com", "testpass123")

        result = await session.execute(select(CompanySettings).limit(1))
        if result.scalar_one_or_none() is None:
            cs = CompanySettings(
                legal_name="Test Co Pte Ltd",
                uen="202300001A",
                address="1 Test Street, Singapore 123456",
                billing_email="billing@test.com",
                default_payment_terms_days=30,
                gst_registered=False,
                jurisdiction="SG",
            )
            session.add(cs)
        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(setup_database) -> AsyncClient:
    """
    HTTP client that overrides get_db to use the test database.
    Each request gets its own session from the test pool — avoids asyncpg
    'another operation in progress' errors from sharing one session.
    """

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Disable app lifespan (it would try to seed into the prod DB)
    from contextlib import asynccontextmanager
    from fastapi import FastAPI

    mock_storage = MockFileStorageService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_file_storage] = lambda: mock_storage

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def auth_headers(client: AsyncClient) -> dict:
    """Bearer token headers for the seeded superadmin."""
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
