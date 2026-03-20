import typer

from acct.api_client import api_get, api_post
from acct.config import clear_credentials, get_api_url, save_credentials
from acct.formatters import print_json, print_success

app = typer.Typer(help="Authentication commands")


@app.command()
def login(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    api_url: str = typer.Option("http://localhost:8000", help="API base URL"),
) -> None:
    """Login and store API token."""
    resp = api_post("/api/auth/login", json_data={"email": email, "password": password})
    token = resp.get("access_token", "")
    refresh_token = resp.get("refresh_token")
    save_credentials(token, api_url, refresh_token=refresh_token)
    print_success(f"Logged in as {email}")


@app.command()
def logout() -> None:
    """Logout and remove stored credentials."""
    clear_credentials()
    print_success("Logged out")


@app.command()
def whoami() -> None:
    """Show current user info."""
    data = api_get("/api/auth/me")
    print_json(data)
