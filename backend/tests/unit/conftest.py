# Unit tests — no database or async fixtures needed.
import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Override the parent conftest's DB fixture — unit tests need no database."""
    yield
