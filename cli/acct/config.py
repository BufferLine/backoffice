import json
import os
import re
from pathlib import Path
from typing import Optional

# ACCT_CONFIG_DIR lets scripts (e.g. scripts/e2e-cli.sh) use throwaway credentials
# without overwriting the operator's own ~/.acct login.
CONFIG_DIR = Path(os.environ.get("ACCT_CONFIG_DIR") or Path.home() / ".acct")
# The default profile keeps the original location, so existing logins keep working.
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_PROFILE = "default"

_PROFILE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_active_profile: Optional[str] = None


class ProfileError(ValueError):
    pass


def _validate(name: str) -> str:
    if not _PROFILE_NAME.match(name):
        raise ProfileError(f"Invalid profile name {name!r}: use 1-32 letters, digits, '-' or '_'")
    return name


def set_profile(name: Optional[str]) -> None:
    """Select the profile for this process (from `acct --profile`). None falls back to ACCT_PROFILE."""
    global _active_profile
    _active_profile = _validate(name) if name else None


def current_profile() -> str:
    name = _active_profile or os.environ.get("ACCT_PROFILE") or DEFAULT_PROFILE
    return _validate(name)


def credentials_file(profile: Optional[str] = None) -> Path:
    name = _validate(profile) if profile else current_profile()
    if name == DEFAULT_PROFILE:
        return CREDENTIALS_FILE
    return CONFIG_DIR / "profiles" / f"{name}.json"


def list_profiles() -> list[dict]:
    """Every saved profile with its server, default first."""
    found = []
    if CREDENTIALS_FILE.exists():
        found.append((DEFAULT_PROFILE, CREDENTIALS_FILE))
    profiles_dir = CONFIG_DIR / "profiles"
    if profiles_dir.is_dir():
        found += sorted((p.stem, p) for p in profiles_dir.glob("*.json") if _PROFILE_NAME.match(p.stem))
    out = []
    for name, path in found:
        try:
            creds = json.loads(path.read_text())
        except (OSError, ValueError):
            creds = {}
        out.append({
            "profile": name,
            "api_url": creds.get("api_url", DEFAULT_API_URL),
            "logged_in": bool(creds.get("token")),
        })
    return out


def check_login_target(api_url: str, replace: bool = False) -> None:
    """Refuse to point a profile that is logged in to one server at a different server.

    Logging in to localhost used to overwrite a production login silently. A different
    server belongs in its own profile (`acct --profile local login ...`), unless the
    caller explicitly asks to replace this profile's server.
    """
    creds = _load_credentials()
    saved = creds.get("api_url")
    if replace or not creds.get("token") or not saved or saved.rstrip("/") == api_url.rstrip("/"):
        return
    profile = current_profile()
    raise ProfileError(
        f"Profile '{profile}' is logged in to {saved}. To log in to {api_url}, use another profile "
        f"(e.g. acct --profile local login --api-url {api_url}) or pass --replace to switch '{profile}'."
    )


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
    path = credentials_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"token": token, "api_url": api_url}
    if refresh_token:
        data["refresh_token"] = refresh_token
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)


def update_token(token: str) -> None:
    """Update only the access token, preserving other credentials."""
    creds = _load_credentials()
    creds["token"] = token
    path = credentials_file()
    path.write_text(json.dumps(creds, indent=2))
    path.chmod(0o600)


def clear_credentials() -> None:
    path = credentials_file()
    if path.exists():
        path.unlink()


def _load_credentials() -> dict:
    path = credentials_file()
    if path.exists():
        return json.loads(path.read_text())
    return {}
