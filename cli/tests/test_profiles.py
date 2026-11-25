"""Credential profiles: a local login must never overwrite a production login."""
import json
from unittest.mock import patch

import pytest

import acct.config as config
from acct.main import app

PROD = "https://backoffice.example.com"
LOCAL = "http://localhost:8000"


@pytest.fixture(autouse=True)
def _isolated(mock_credentials, monkeypatch):
    monkeypatch.delenv("ACCT_PROFILE", raising=False)
    monkeypatch.setattr(config, "_active_profile", None)
    yield mock_credentials


@pytest.fixture
def me():
    with patch("acct.commands.auth.api_get", return_value={"email": "admin@example.com"}) as m:
        yield m


def _read(path):
    return json.loads(path.read_text())


def test_default_profile_keeps_the_original_file(_isolated):
    config.save_credentials("t1", PROD)
    assert config.credentials_file() == config.CREDENTIALS_FILE
    assert _read(config.CREDENTIALS_FILE)["api_url"] == PROD


def test_named_profile_login_leaves_default_untouched(runner, me, _isolated):
    config.save_credentials("prod-token", PROD)
    result = runner.invoke(app, ["--profile", "local", "login", "--token", "dev-token", "--api-url", LOCAL])
    assert result.exit_code == 0, result.output
    assert "profile: local" in result.output
    assert _read(config.CREDENTIALS_FILE) == {"token": "prod-token", "api_url": PROD}
    assert _read(_isolated / "profiles" / "local.json")["api_url"] == LOCAL


def test_login_to_another_server_in_same_profile_is_refused(runner, me):
    config.save_credentials("prod-token", PROD)
    result = runner.invoke(app, ["login", "--token", "dev-token", "--api-url", LOCAL])
    assert result.exit_code == 1
    assert "--profile local" in result.output
    assert _read(config.CREDENTIALS_FILE) == {"token": "prod-token", "api_url": PROD}
    me.assert_not_called()


def test_replace_switches_the_profile_server(runner, me):
    config.save_credentials("prod-token", PROD)
    result = runner.invoke(app, ["login", "--token", "dev-token", "--api-url", LOCAL, "--replace"])
    assert result.exit_code == 0, result.output
    assert _read(config.CREDENTIALS_FILE)["api_url"] == LOCAL


def test_relogin_to_the_same_server_is_allowed(runner, me):
    config.save_credentials("old", PROD)
    result = runner.invoke(app, ["login", "--token", "new", "--api-url", PROD + "/"])
    assert result.exit_code == 0, result.output
    assert _read(config.CREDENTIALS_FILE)["token"] == "new"


def test_init_is_guarded_too(runner):
    config.save_credentials("prod-token", PROD)
    with patch("acct.main.api_post") as post:
        result = runner.invoke(app, ["init", "--company-name", "X", "--jurisdiction", "SG", "--uen", "", "--api-url", LOCAL])
    assert result.exit_code == 1
    post.assert_not_called()
    assert _read(config.CREDENTIALS_FILE)["api_url"] == PROD


def test_env_var_selects_profile(monkeypatch, _isolated):
    monkeypatch.setenv("ACCT_PROFILE", "local")
    config.save_credentials("dev", LOCAL)
    assert config.get_api_url() == LOCAL
    assert (_isolated / "profiles" / "local.json").exists()
    assert not config.CREDENTIALS_FILE.exists()


def test_invalid_profile_name_is_rejected(runner):
    result = runner.invoke(app, ["--profile", "../prod", "profiles"])
    assert result.exit_code == 2


def test_profiles_lists_each_server(runner):
    config.save_credentials("prod-token", PROD)
    config.set_profile("local")
    config.save_credentials("dev", LOCAL)
    config.set_profile(None)
    result = runner.invoke(app, ["profiles"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("* default") and PROD in lines[0]
    assert "local" in lines[1] and LOCAL in lines[1]
