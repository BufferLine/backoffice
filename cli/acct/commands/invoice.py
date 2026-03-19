from pathlib import Path
from typing import Optional

import typer

from acct.api_client import api_delete, api_download, api_get, api_patch, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Invoice management commands")


@app.command()
def create(
    client: str = typer.Option(..., "--client", help="Client ID"),
    currency: str = typer.Option("SGD", "--currency", help="Invoice currency code"),
    description: str = typer.Option("", "--description", help="Invoice description"),
) -> None:
    """Create a new draft invoice."""
    data = api_post(
        "/api/invoices",
        json_data={"client_id": client, "currency": currency, "description": description},
    )
    print_success(f"Invoice created: {data['id']}")
    print_json(data)


@app.command()
def edit(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
    description: Optional[str] = typer.Option(None, "--description", help="Invoice description"),
    due_date: Optional[str] = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)"),
) -> None:
    """Edit an existing draft invoice."""
    payload: dict = {}
    if description is not None:
        payload["description"] = description
    if due_date is not None:
        payload["due_date"] = due_date
    data = api_patch(f"/api/invoices/{invoice_id}", json_data=payload)
    print_success(f"Invoice {invoice_id} updated")
    print_json(data)


@app.command()
def add_item(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
    desc: str = typer.Option(..., "--desc", help="Line item description"),
    qty: float = typer.Option(..., "--qty", help="Quantity"),
    price: float = typer.Option(..., "--price", help="Unit price"),
) -> None:
    """Add a line item to an invoice."""
    data = api_post(
        f"/api/invoices/{invoice_id}/line-items",
        json_data={"description": desc, "quantity": qty, "unit_price": price},
    )
    print_success(f"Item added to invoice {invoice_id}")
    print_json(data)


@app.command()
def issue(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
) -> None:
    """Issue (send) a draft invoice."""
    data = api_post(f"/api/invoices/{invoice_id}/issue")
    print_success(f"Invoice {invoice_id} issued")
    print_json(data)


@app.command()
def mark_paid(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
    payment_id: str = typer.Option(..., "--payment-id", help="Payment ID"),
) -> None:
    """Mark an invoice as paid."""
    data = api_post(
        f"/api/invoices/{invoice_id}/mark-paid",
        json_data={"payment_id": payment_id},
    )
    print_success(f"Invoice {invoice_id} marked as paid")
    print_json(data)


@app.command()
def cancel(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
) -> None:
    """Cancel an invoice."""
    data = api_post(f"/api/invoices/{invoice_id}/cancel")
    print_success(f"Invoice {invoice_id} cancelled")
    print_json(data)


@app.command(name="list")
def list_invoices(
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Filter by status: draft|issued|paid|cancelled",
    ),
) -> None:
    """List invoices."""
    params: dict = {}
    if status:
        params["status"] = status
    data = api_get("/api/invoices", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Invoices",
        ["ID", "Client", "Currency", "Total", "Status", "Due Date"],
        [
            [
                inv.get("id", ""),
                inv.get("client_id", ""),
                inv.get("currency", ""),
                inv.get("total", ""),
                inv.get("status", ""),
                inv.get("due_date", ""),
            ]
            for inv in items
        ],
    )


@app.command()
def show(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
) -> None:
    """Show invoice details."""
    data = api_get(f"/api/invoices/{invoice_id}")
    print_json(data)


@app.command()
def attach(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
    filepath: Path = typer.Argument(..., help="File path to attach", exists=True),
) -> None:
    """Attach a file to an invoice."""
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f, "application/octet-stream")}
        data = api_post(f"/api/invoices/{invoice_id}/attachments", files=files)
    print_success(f"File attached to invoice {invoice_id}")
    print_json(data)


@app.command()
def download(
    invoice_id: str = typer.Argument(..., help="Invoice ID"),
    output: str = typer.Option(".", "-o", "--output", help="Output directory or file path"),
) -> None:
    """Download invoice PDF."""
    filepath = api_download(f"/api/invoices/{invoice_id}/pdf", output)
    print_success(f"Downloaded: {filepath}")
