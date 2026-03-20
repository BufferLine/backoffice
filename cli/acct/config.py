import json
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".acct"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
DEFAULT_API_URL = "http://localhost:8000"


def get_api_url() -> str:
    creds = _load_credentials()
    return creds.get("api_url", DEFAULT_API_URL)


def get_token() -> Optional[str]:
    creds = _load_credentials()
    return creds.get("token")


def get_refresh_token() -> Optional[str]:
    creds = _load_credentials()
    return creds.get("refresh_token")


def save_credentials(token: str, api_url: str = DEFAULT_API_URL, refresh_token: Optional[str] = None) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"token": token, "api_url": api_url}
    if refresh_token:
        data["refresh_token"] = refresh_token
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    CREDENTIALS_FILE.chmod(0o600)


def update_token(token: str) -> None:
    """Update only the access token, preserving other credentials."""
    creds = _load_credentials()
    creds["token"] = token
    CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2))
    CREDENTIALS_FILE.chmod(0o600)


def clear_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()


def _load_credentials() -> dict:
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text())
    return {}
