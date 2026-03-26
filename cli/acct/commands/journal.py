from datetime import date
from typing import Optional

import typer

from acct.api_client import api_delete, api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Journal entry commands (double-entry bookkeeping)")


@app.command()
def create(
    entry_date: str = typer.Option(..., "--date", help="Entry date (YYYY-MM-DD)"),
    debit: str = typer.Option(..., "--debit", help="ACCOUNT_ID:AMOUNT (e.g. uuid:60000)"),
    credit: str = typer.Option(..., "--credit", help="ACCOUNT_ID:AMOUNT (e.g. uuid:60000)"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    description: str = typer.Option(None, "--description", help="Journal entry description"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="Auto-confirm the entry"),
) -> None:
    """Create a journal entry with one debit and one credit line."""
    debit_parts = debit.rsplit(":", 1)
    credit_parts = credit.rsplit(":", 1)
    if len(debit_parts) != 2 or len(credit_parts) != 2:
        typer.echo("Error: --debit and --credit must be ACCOUNT_ID:AMOUNT", err=True)
        raise typer.Exit(1)

    data = api_post(
        "/api/journal-entries",
        json_data={
            "entry_date": entry_date,
            "description": description,
            "is_confirmed": confirm,
            "lines": [
                {
                    "account_id": debit_parts[0],
                    "debit": debit_parts[1],
                    "credit": "0",
                    "currency": currency,
                },
                {
                    "account_id": credit_parts[0],
                    "debit": "0",
                    "credit": credit_parts[1],
                    "currency": currency,
                },
            ],
        },
    )
    print_success(f"Journal entry created: {data.get('id', '')}")
    print_json(data)


@app.command("list")
def list_entries(
    page: int = typer.Option(1, "--page"),
    confirmed: Optional[bool] = typer.Option(None, "--confirmed/--unconfirmed", help="Filter by status"),
    from_date: Optional[str] = typer.Option(None, "--from", help="From date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="To date (YYYY-MM-DD)"),
) -> None:
    """List journal entries."""
    params: dict = {"page": page}
    if confirmed is not None:
        params["confirmed"] = str(confirmed).lower()
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    data = api_get("/api/journal-entries", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Journal Entries",
        ["ID", "Date", "Description", "Confirmed", "Lines"],
        [
            [
                e.get("id", "")[:8],
                e.get("entry_date", ""),
                (e.get("description") or "")[:40],
                "Yes" if e.get("is_confirmed") else "No",
                str(len(e.get("lines", []))),
            ]
            for e in items
        ],
    )


@app.command()
def show(
    entry_id: str = typer.Argument(..., help="Journal entry ID"),
) -> None:
    """Show journal entry details."""
    data = api_get(f"/api/journal-entries/{entry_id}")
    print_json(data)


@app.command()
def confirm(
    entry_id: str = typer.Argument(..., help="Journal entry ID"),
) -> None:
    """Confirm an unconfirmed journal entry."""
    data = api_post(f"/api/journal-entries/{entry_id}/confirm")
    print_success(f"Journal entry {entry_id} confirmed")
    print_json(data)


@app.command()
def delete(
    entry_id: str = typer.Argument(..., help="Journal entry ID"),
) -> None:
    """Delete an unconfirmed journal entry."""
    api_delete(f"/api/journal-entries/{entry_id}")
    print_success(f"Journal entry {entry_id} deleted")
