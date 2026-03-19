from pathlib import Path
from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Bank statement and transaction commands")


@app.command()
def statement_upload(
    filepath: Path = typer.Argument(..., help="Bank statement file path", exists=True),
    source: str = typer.Option(..., "--source", help="Statement source: airwallex|dbs|ocbc"),
) -> None:
    """Upload a bank statement for reconciliation."""
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f, "application/octet-stream")}
        data = api_post(
            f"/api/bank-statements/upload?source={source}",
            files=files,
        )
    print_success(f"Bank statement uploaded: {data.get('id', '')}")
    print_json(data)


@app.command()
def tx_list(
    status: Optional[str] = typer.Option(
        None, "--status", help="Filter by status: unmatched|matched|ignored"
    ),
) -> None:
    """List bank transactions."""
    params: dict = {}
    if status:
        params["match_status"] = status
    data = api_get("/api/bank-transactions", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Bank Transactions",
        ["ID", "Date", "Description", "Amount", "Currency", "Match Status", "Payment ID"],
        [
            [
                tx.get("id", ""),
                tx.get("tx_date", ""),
                tx.get("description", ""),
                tx.get("amount", ""),
                tx.get("currency", ""),
                tx.get("match_status", ""),
                tx.get("matched_payment_id", ""),
            ]
            for tx in items
        ],
    )


@app.command()
def tx_match(
    tx_id: str = typer.Argument(..., help="Bank transaction ID"),
    payment_id: str = typer.Option(..., "--payment-id", help="Payment ID to match against"),
) -> None:
    """Manually match a bank transaction to a payment."""
    data = api_post(
        f"/api/bank-transactions/{tx_id}/match",
        json_data={"payment_id": payment_id},
    )
    print_success(f"Transaction {tx_id} matched to payment {payment_id}")
    print_json(data)


@app.command()
def tx_auto_match() -> None:
    """Auto-match unmatched bank transactions to payments."""
    data = api_post("/api/bank-transactions/auto-match")
    matched = data.get("matched", 0)
    print_success(f"Auto-matched {matched} transactions")
    print_json(data)


@app.command()
def tx_ignore(
    tx_id: str = typer.Argument(..., help="Bank transaction ID to ignore"),
) -> None:
    """Mark a bank transaction as ignored (no matching needed)."""
    data = api_post(f"/api/bank-transactions/{tx_id}/ignore")
    print_success(f"Transaction {tx_id} marked as ignored")
    print_json(data)
