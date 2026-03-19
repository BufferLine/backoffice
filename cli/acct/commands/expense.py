from pathlib import Path
from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Expense management commands")


@app.command()
def add(
    date: str = typer.Option(..., "--date", help="Expense date (YYYY-MM-DD)"),
    vendor: str = typer.Option(..., "--vendor", help="Vendor name"),
    category: str = typer.Option(..., "--category", help="Expense category"),
    amount: float = typer.Option(..., "--amount", help="Expense amount"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    description: str = typer.Option("", "--description", help="Optional description"),
) -> None:
    """Add a new expense."""
    data = api_post(
        "/api/expenses",
        json_data={
            "date": date,
            "vendor": vendor,
            "category": category,
            "amount": amount,
            "currency": currency,
            "description": description,
        },
    )
    print_success(f"Expense added: {data['id']}")
    print_json(data)


@app.command()
def confirm(
    expense_id: str = typer.Argument(..., help="Expense ID"),
) -> None:
    """Confirm a pending expense."""
    data = api_post(f"/api/expenses/{expense_id}/confirm")
    print_success(f"Expense {expense_id} confirmed")
    print_json(data)


@app.command()
def reimburse(
    expense_id: str = typer.Argument(..., help="Expense ID"),
    payment_id: str = typer.Option(..., "--payment-id", help="Payment ID"),
) -> None:
    """Mark an expense as reimbursed."""
    data = api_post(
        f"/api/expenses/{expense_id}/reimburse",
        json_data={"payment_id": payment_id},
    )
    print_success(f"Expense {expense_id} reimbursed")
    print_json(data)


@app.command(name="list")
def list_expenses(
    month: Optional[str] = typer.Option(None, "--month", help="Filter by month (YYYY-MM)"),
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category"),
) -> None:
    """List expenses."""
    params: dict = {}
    if month:
        params["month"] = month
    if category:
        params["category"] = category
    data = api_get("/api/expenses", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Expenses",
        ["ID", "Date", "Vendor", "Category", "Amount", "Currency", "Status"],
        [
            [
                exp.get("id", ""),
                exp.get("date", ""),
                exp.get("vendor", ""),
                exp.get("category", ""),
                exp.get("amount", ""),
                exp.get("currency", ""),
                exp.get("status", ""),
            ]
            for exp in items
        ],
    )


@app.command()
def attach(
    expense_id: str = typer.Argument(..., help="Expense ID"),
    filepath: Path = typer.Argument(..., help="Receipt file path to attach", exists=True),
) -> None:
    """Attach a receipt to an expense."""
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f, "application/octet-stream")}
        data = api_post(f"/api/expenses/{expense_id}/attachments", files=files)
    print_success(f"Receipt attached to expense {expense_id}")
    print_json(data)
