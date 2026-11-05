from typing import Optional

import typer

from acct.api_client import api_get, api_patch
from acct.formatters import print_json, print_success

app = typer.Typer(help="Ledger account mapping for automatic journal postings")


@app.command()
def show() -> None:
    """Show which accounts invoice, receipt, and FX postings use."""
    data = api_get("/api/ledger/accounts")
    if not data.get("configured"):
        typer.echo("Ledger posting is OFF: set at least --receivable and --revenue to enable it.")
    print_json(data)


@app.command(name="set")
def set_accounts(
    receivable: Optional[list[str]] = typer.Option(
        None, "--receivable",
        help="Receivable account per invoice currency as CCY=<account-id> (repeatable), e.g. --receivable USD=<id>",
    ),
    revenue: Optional[str] = typer.Option(None, "--revenue", help="Revenue account ID (SGD, class revenue)"),
    gst_output: Optional[str] = typer.Option(None, "--gst-output", help="GST output tax account ID (SGD, class liability)"),
    fx_gain_loss: Optional[str] = typer.Option(
        None, "--fx-gain-loss", help="Realised FX gain/loss account ID (SGD, class revenue or expense)",
    ),
) -> None:
    """Set ledger accounts. Omitted options keep their current value.

    Once --receivable and --revenue are set, issuing an invoice posts
    Dr Receivable / Cr Revenue (+ GST output) automatically.
    """
    payload: dict = {}
    if receivable:
        mapping: dict[str, str] = {}
        for item in receivable:
            ccy, sep, account_id = item.partition("=")
            if not sep or not ccy or not account_id:
                raise typer.BadParameter(f"--receivable expects CCY=<account-id>, got {item!r}")
            mapping[ccy.strip().upper()] = account_id.strip()
        payload["receivable"] = mapping
    if revenue:
        payload["revenue"] = revenue
    if gst_output:
        payload["gst_output"] = gst_output
    if fx_gain_loss:
        payload["fx_gain_loss"] = fx_gain_loss
    if not payload:
        raise typer.BadParameter("Nothing to set; pass at least one option")
    data = api_patch("/api/ledger/accounts", json_data=payload)
    print_success("Ledger accounts updated")
    print_json(data)
