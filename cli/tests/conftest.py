"""Pytest configuration and fixtures for CLI tests."""
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from acct.main import app


@pytest.fixture
def runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_api_get():
    """Mock api_get to avoid real HTTP calls."""
    with patch("acct.api_client.api_get") as mock:
        yield mock


@pytest.fixture
def mock_api_post():
    """Mock api_post to avoid real HTTP calls."""
    with patch("acct.api_client.api_post") as mock:
        yield mock


@pytest.fixture
def mock_api_patch():
    """Mock api_patch to avoid real HTTP calls."""
    with patch("acct.api_client.api_patch") as mock:
        yield mock


@pytest.fixture
def mock_credentials(tmp_path, monkeypatch):
    """Redirect credentials storage to a temp directory."""
    import acct.config as config

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / ".acct")
    monkeypatch.setattr(config, "CREDENTIALS_FILE", tmp_path / ".acct" / "credentials.json")
    return tmp_path / ".acct"
