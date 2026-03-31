from pathlib import Path
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
        "related_entity_type": entity_type,
        "related_entity_id": entity_id,
        "amount": amount,
        "currency": currency,
    }
    if tx_hash:
        payload["tx_hash"] = tx_hash
    if chain:
        payload["chain_id"] = chain
    if date:
        payload["payment_date"] = date
    if reference:
        payload["bank_reference"] = reference
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
                f"{p.get('related_entity_type', '')}:{p.get('related_entity_id', '')}",
                p.get("amount", ""),
                p.get("currency", ""),
                p.get("payment_date", ""),
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


@app.command()
def pipeline(
    entity: str = typer.Option(
        ..., "--entity", help="Entity reference, e.g. payroll_run:<id> or invoice:<id> or loan:<id>"
    ),
    type: str = typer.Option("bank_transfer", "--type", help="Payment type: bank_transfer|crypto|cash"),
) -> None:
    """Auto-create payment from entity with proof attachment and bank matching."""
    entity_type, _, entity_id = entity.partition(":")
    payload: dict = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payment_type": type,
    }
    data = api_post("/api/payments/pipeline", json_data=payload)
    payment = data.get("payment", {})
    print_success(f"Payment created: {payment.get('id', '')}")
    print_success(f"Reference: {payment.get('reference_number', 'N/A')}")
    if payment.get("proof_file_id"):
        print_success("Proof document auto-attached")
    if data.get("bank_match_tx_id"):
        print_success(
            f"Bank transaction matched: {data['bank_match_tx_id']} "
            f"(confidence: {data.get('bank_match_confidence', 'N/A')})"
        )
    else:
        typer.echo("No bank transaction match found (will retry on next statement import)")
    print_json(data)


@app.command()
def attach(
    payment_id: str = typer.Argument(..., help="Payment ID"),
    filepath: Path = typer.Argument(..., help="File path to attach", exists=True),
) -> None:
    """Attach a proof/evidence file to a payment."""
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f, "application/octet-stream")}
        data = api_post(f"/api/payments/{payment_id}/attach-proof", files=files)
    print_success(f"Proof attached to payment {payment_id}")
    print_json(data)


@app.command()
def allocate(
    payment_id: str = typer.Argument(..., help="Payment ID"),
    entity: str = typer.Option(..., "--entity", help="Entity reference, e.g. loan:<id>"),
    amount: float = typer.Option(..., "--amount", help="Amount to allocate"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Allocation notes"),
) -> None:
    """Allocate a payment to an entity (e.g. loan)."""
    entity_type, _, entity_id = entity.partition(":")
    allocation: dict = {"entity_type": entity_type, "entity_id": entity_id, "amount": amount}
    if notes:
        allocation["notes"] = notes
    data = api_post(f"/api/payments/{payment_id}/allocate", json_data={"allocations": [allocation]})
    print_success(f"Payment {payment_id} allocated")
    print_json(data)
