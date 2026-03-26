from typing import Optional

import typer

from acct.api_client import api_delete, api_get, api_post
from acct.config import clear_credentials, get_api_url, save_credentials
from acct.formatters import print_json, print_success, print_table, print_error

app = typer.Typer(help="Authentication commands")


@app.command()
def login(
    email: str = typer.Option(None, help="Email address"),
    password: str = typer.Option(None, help="Password", hide_input=True),
    token: str = typer.Option(None, help="API token (alternative to email/password)"),
    api_url: str = typer.Option("http://localhost:8000", help="API base URL"),
) -> None:
    """Login with email/password or API token."""
    if token:
        save_credentials(token, api_url)
        # Verify the token works
        data = api_get("/api/auth/me")
        print_success(f"Logged in as {data['email']} (via API token)")
    elif email and password:
        save_credentials("", api_url)
        resp = api_post("/api/auth/login", json_data={"email": email, "password": password})
        access_token = resp.get("access_token", "")
        refresh_token = resp.get("refresh_token")
        save_credentials(access_token, api_url, refresh_token=refresh_token)
        print_success(f"Logged in as {email}")
    else:
        # Interactive prompts
        if not email:
            email = typer.prompt("Email")
        if not password:
            password = typer.prompt("Password", hide_input=True)
        save_credentials("", api_url)
        resp = api_post("/api/auth/login", json_data={"email": email, "password": password})
        access_token = resp.get("access_token", "")
        refresh_token = resp.get("refresh_token")
        save_credentials(access_token, api_url, refresh_token=refresh_token)
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


@app.command("create-token")
def create_token(
    name: str = typer.Option(..., help="Token name"),
) -> None:
    """Create an API token for CLI or automation use."""
    resp = api_post("/api/auth/api-tokens", json_data={"name": name})
    print_success(f"API token created: {resp['name']}")
    typer.echo(f"\nToken: {resp['token']}")
    typer.echo("\nSave this token — it won't be shown again.")
    typer.echo(f"Login with: acct login --token <token> --api-url {get_api_url()}")


@app.command("list-tokens")
def list_tokens() -> None:
    """List your API tokens."""
    data = api_get("/api/auth/api-tokens")
    if not data:
        typer.echo("No API tokens found.")
        return
    columns = ["ID", "Name", "Last Used", "Expires", "Created"]
    rows = [
        [t["id"], t["name"], t.get("last_used_at") or "-", t.get("expires_at") or "never", t["created_at"]]
        for t in data
    ]
    print_table("API Tokens", columns, rows)


@app.command("revoke-token")
def revoke_token(
    token_id: str = typer.Argument(..., help="Token ID to revoke"),
) -> None:
    """Revoke an API token."""
    api_delete(f"/api/auth/api-tokens/{token_id}")
    print_success(f"Token {token_id} revoked")
