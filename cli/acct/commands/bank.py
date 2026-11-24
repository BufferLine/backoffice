from pathlib import Path
from typing import Optional

import typer

from acct.amounts import decimal_amount
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
def tx_reconcile(
    tx_id: str = typer.Argument(..., help="Bank transaction ID"),
    bank_account: str = typer.Option(..., "--bank-account", help="Bank account ID (asset)"),
    contra_account: Optional[str] = typer.Option(
        None, "--contra-account",
        help="Contra account ID (expense/revenue/etc). Omit for a deposit matched to an invoice payment: "
        "it settles the invoice receivable",
    ),
    description: Optional[str] = typer.Option(None, "--description", help="Journal entry description"),
    no_confirm: bool = typer.Option(False, "--no-confirm", help="Create as unconfirmed"),
    fx_rate: Optional[str] = typer.Option(
        None, "--fx-rate", help="SGD per 1 unit, for a foreign-currency invoice settlement", callback=decimal_amount,
    ),
) -> None:
    """Reconcile a bank transaction by creating a journal entry."""
    payload: dict = {
        "bank_account_id": bank_account,
        "contra_account_id": contra_account,
        "description": description,
        "auto_confirm": not no_confirm,
    }
    if fx_rate:
        payload["fx_rate_to_sgd"] = fx_rate
    data = api_post(f"/api/bank-transactions/{tx_id}/reconcile", json_data=payload)
    print_success(f"Transaction {tx_id} reconciled")
    print_json(data)


@app.command()
def tx_ignore(
    tx_id: str = typer.Argument(..., help="Bank transaction ID to ignore"),
) -> None:
    """Mark a bank transaction as ignored (no matching needed)."""
    data = api_post(f"/api/bank-transactions/{tx_id}/ignore")
    print_success(f"Transaction {tx_id} marked as ignored")
    print_json(data)


@app.command()
def tx_link(
    journal: str = typer.Option(..., "--journal", help="Confirmed journal entry ID the rows are reconciled into"),
    tx: Optional[list[str]] = typer.Option(None, "--tx", help="Bank transaction ID (repeatable)"),
    coinbase_order: Optional[list[str]] = typer.Option(
        None, "--coinbase-order", help="Coinbase order ID: links every fill of that order (repeatable)",
    ),
    description: Optional[str] = typer.Option(None, "--description", help="Note for the audit log"),
) -> None:
    """Reconcile bank rows into an already-posted journal entry.

    The rows' amounts must add up, per account, to exactly what the entry moves on that
    account — e.g. all fills of a Coinbase order against one conversion entry.
    """
    if not tx and not coinbase_order:
        raise typer.BadParameter("pass --tx and/or --coinbase-order")
    data = api_post(
        "/api/bank-transactions/link",
        json_data={
            "journal_entry_id": journal,
            "tx_ids": tx or [],
            "coinbase_order_ids": coinbase_order or [],
            "description": description,
        },
    )
    print_success(f"Linked {len(data.get('linked', []))} bank transaction(s) to journal entry {journal}")
    print_json(data)
