from typing import Optional

import typer

from acct.api_client import api_post
from acct.config import save_credentials
from acct.formatters import print_success

app = typer.Typer(help="Initialize the backoffice system")


@app.callback(invoke_without_command=True)
def init(
    company_name: str = typer.Option(..., prompt="Company name"),
    jurisdiction: str = typer.Option("SG", prompt="Jurisdiction (SG, KR, etc.)"),
    uen: str = typer.Option("", prompt="UEN (optional, press enter to skip)"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
) -> None:
    """Initialize the backoffice system."""
    # Save api_url to credentials first (empty token)
    save_credentials("", api_url)

    resp = api_post(
        "/api/setup/init",
        json_data={
            "company_name": company_name,
            "jurisdiction": jurisdiction,
            "uen": uen or None,
        },
    )

    setup_url = resp["setup_url"]
    print_success("System initialized!")
    typer.echo(f"\nOpen this link in your browser to create your admin account:\n")
    typer.echo(f"  {setup_url}\n")
    typer.echo(f"This link expires in 1 hour and can only be used once.")
