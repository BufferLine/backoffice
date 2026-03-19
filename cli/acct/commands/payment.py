from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Payment recording commands")


@app.command()
def record(
    type: str = typer.Option(..., "--type", help="Payment type: bank_transfer|crypto|cash"),
    entity: str = typer.Option(
        ..., "--entity", help="Entity reference, e.g. invoice:<id> or payroll_run:<id>"
    ),
    amount: float = typer.Option(..., "--amount", help="Payment amount"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    tx_hash: Optional[str] = typer.Option(None, "--tx-hash", help="Crypto transaction hash"),
    chain: Optional[str] = typer.Option(None, "--chain", help="Blockchain network name"),
    date: Optional[str] = typer.Option(None, "--date", help="Payment date (YYYY-MM-DD)"),
    reference: Optional[str] = typer.Option(None, "--reference", help="Bank reference number"),
) -> None:
    """Record a payment against an entity."""
    entity_type, _, entity_id = entity.partition(":")
    payload: dict = {
        "payment_type": type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "amount": amount,
        "currency": currency,
    }
    if tx_hash:
        payload["tx_hash"] = tx_hash
    if chain:
        payload["chain"] = chain
    if date:
        payload["date"] = date
    if reference:
        payload["reference"] = reference
    data = api_post("/api/payments", json_data=payload)
    print_success(f"Payment recorded: {data['id']}")
    print_json(data)


@app.command(name="list")
def list_payments(
    entity_type: Optional[str] = typer.Option(
        None, "--entity-type", help="Filter by entity type: invoice|payroll_run|expense"
    ),
) -> None:
    """List payments."""
    params: dict = {}
    if entity_type:
        params["entity_type"] = entity_type
    data = api_get("/api/payments", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Payments",
        ["ID", "Type", "Entity", "Amount", "Currency", "Date"],
        [
            [
                p.get("id", ""),
                p.get("payment_type", ""),
                f"{p.get('entity_type', '')}:{p.get('entity_id', '')}",
                p.get("amount", ""),
                p.get("currency", ""),
                p.get("date", ""),
            ]
            for p in items
        ],
    )


@app.command()
def show(
    payment_id: str = typer.Argument(..., help="Payment ID"),
) -> None:
    """Show payment details."""
    data = api_get(f"/api/payments/{payment_id}")
    print_json(data)
