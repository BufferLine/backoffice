from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Client management")


@app.command()
def create(
    name: str = typer.Option(..., "--name", help="Legal name"),
    email: str = typer.Option("", "--email", help="Billing email"),
    address: str = typer.Option("", "--address", help="Billing address"),
    currency: str = typer.Option("SGD", "--currency", help="Default currency"),
    payment_terms: int = typer.Option(30, "--payment-terms", help="Payment terms in days"),
) -> None:
    """Create a new client."""
    data = api_post(
        "/api/clients",
        json_data={
            "legal_name": name,
            "billing_email": email or None,
            "billing_address": address or None,
            "default_currency": currency,
            "payment_terms_days": payment_terms,
        },
    )
    print_success(f"Client created: {data['id']}")
    print_json(data)


@app.command(name="list")
def list_clients() -> None:
    """List all clients."""
    data = api_get("/api/clients")
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Clients",
        ["ID", "Name", "Email", "Currency", "Payment Terms"],
        [
            [
                c.get("id", ""),
                c.get("legal_name", ""),
                c.get("billing_email", ""),
                c.get("default_currency", ""),
                str(c.get("payment_terms_days", "")),
            ]
            for c in items
        ],
    )


@app.command()
def show(
    client_id: str = typer.Argument(..., help="Client ID"),
) -> None:
    """Show client details."""
    data = api_get(f"/api/clients/{client_id}")
    print_json(data)
