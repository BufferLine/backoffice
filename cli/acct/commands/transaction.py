from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Transaction management commands")


@app.command(name="list")
def list_transactions(
    account_id: Optional[str] = typer.Option(None, "--account", help="Filter by account ID"),
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category"),
    tx_status: Optional[str] = typer.Option(None, "--status", help="Filter by status: pending|confirmed|cancelled"),
    start_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    page: int = typer.Option(1, "--page", help="Page number"),
    per_page: int = typer.Option(20, "--per-page", help="Items per page"),
) -> None:
    """List transactions."""
    params: dict = {"page": page, "per_page": per_page}
    if account_id:
        params["account_id"] = account_id
    if category:
        params["category"] = category
    if tx_status:
        params["tx_status"] = tx_status
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    data = api_get("/api/transactions", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Transactions",
        ["ID", "Account", "Direction", "Amount", "Currency", "Date", "Status", "Category"],
        [
            [
                t.get("id", ""),
                t.get("account_id", ""),
                t.get("direction", ""),
                t.get("amount", ""),
                t.get("currency", ""),
                t.get("tx_date", ""),
                t.get("status", ""),
                t.get("category", ""),
            ]
            for t in items
        ],
    )


@app.command()
def create(
    account_id: str = typer.Option(..., "--account", help="Account ID"),
    direction: str = typer.Option(..., "--direction", help="Direction: in or out"),
    amount: float = typer.Option(..., "--amount", help="Amount"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    tx_date: str = typer.Option(..., "--date", help="Transaction date (YYYY-MM-DD)"),
    category: str = typer.Option(..., "--category", help="Transaction category"),
    counterparty: Optional[str] = typer.Option(None, "--counterparty", help="Counterparty name"),
    description: Optional[str] = typer.Option(None, "--description", help="Description"),
    reference: Optional[str] = typer.Option(None, "--reference", help="Reference"),
    tx_status: str = typer.Option("pending", "--status", help="Status: pending|confirmed"),
) -> None:
    """Create a new transaction."""
    payload: dict = {
        "account_id": account_id,
        "direction": direction,
        "amount": str(amount),
        "currency": currency,
        "tx_date": tx_date,
        "category": category,
        "status": tx_status,
    }
    if counterparty:
        payload["counterparty"] = counterparty
    if description:
        payload["description"] = description
    if reference:
        payload["reference"] = reference
    data = api_post("/api/transactions", json_data=payload)
    print_success(f"Transaction created: {data['id']}")
    print_json(data)


@app.command()
def confirm(
    tx_id: str = typer.Argument(..., help="Transaction ID"),
) -> None:
    """Confirm a pending transaction."""
    data = api_post(f"/api/transactions/{tx_id}/confirm", json_data={})
    print_success(f"Transaction confirmed: {data['id']}")
    print_json(data)


@app.command()
def cancel(
    tx_id: str = typer.Argument(..., help="Transaction ID"),
) -> None:
    """Cancel a pending transaction."""
    data = api_post(f"/api/transactions/{tx_id}/cancel", json_data={})
    print_success(f"Transaction cancelled: {data['id']}")
    print_json(data)
