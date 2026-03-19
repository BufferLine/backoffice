from typing import Optional

import typer

from acct.api_client import api_delete, api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Recurring commitment commands")


@app.command(name="list")
def list_commitments(
    page: int = typer.Option(1, "--page", help="Page number"),
    per_page: int = typer.Option(20, "--per-page", help="Items per page"),
) -> None:
    """List recurring commitments."""
    params: dict = {"page": page, "per_page": per_page}
    data = api_get("/api/recurring-commitments", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Recurring Commitments",
        ["ID", "Name", "Category", "Currency", "Amount", "Frequency", "Active"],
        [
            [
                c.get("id", ""),
                c.get("name", ""),
                c.get("category", ""),
                c.get("currency", ""),
                c.get("expected_amount", ""),
                c.get("frequency", ""),
                str(c.get("is_active", "")),
            ]
            for c in items
        ],
    )


@app.command()
def add(
    name: str = typer.Option(..., "--name", help="Commitment name"),
    category: str = typer.Option(..., "--category", help="Outflow category"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    amount: float = typer.Option(..., "--amount", help="Expected amount"),
    frequency: str = typer.Option(..., "--frequency", help="Frequency: monthly|quarterly|yearly"),
    account_id: Optional[str] = typer.Option(None, "--account", help="Account ID"),
    vendor: Optional[str] = typer.Option(None, "--vendor", help="Vendor name"),
    day_of_period: Optional[int] = typer.Option(None, "--day", help="Day of period (1-28)"),
) -> None:
    """Add a new recurring commitment."""
    payload: dict = {
        "name": name,
        "category": category,
        "currency": currency,
        "expected_amount": str(amount),
        "frequency": frequency,
    }
    if account_id:
        payload["account_id"] = account_id
    if vendor:
        payload["vendor"] = vendor
    if day_of_period is not None:
        payload["day_of_period"] = day_of_period
    data = api_post("/api/recurring-commitments", json_data=payload)
    print_success(f"Commitment created: {data['id']}")
    print_json(data)


@app.command()
def deactivate(
    commitment_id: str = typer.Argument(..., help="Commitment ID"),
) -> None:
    """Deactivate a recurring commitment."""
    data = api_delete(f"/api/recurring-commitments/{commitment_id}")
    print_success(f"Commitment deactivated: {data['id']}")
    print_json(data)
