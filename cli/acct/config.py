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


def save_credentials(token: str, api_url: str = DEFAULT_API_URL) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps({"token": token, "api_url": api_url}, indent=2))
    CREDENTIALS_FILE.chmod(0o600)


def clear_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()


def _load_credentials() -> dict:
    if CREDENTIALS_FILE.exists():
        return json.loads(CREDENTIALS_FILE.read_text())
    return {}
