from typing import Optional

import typer

from acct.amounts import decimal_amount
from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="FX conversion recording commands")


@app.command()
def record(
    sell_currency: str = typer.Option(..., "--sell-currency", help="Currency to sell (e.g. SGD)"),
    sell_amount: str = typer.Option(..., "--sell-amount", help="Amount to sell", callback=decimal_amount),
    buy_currency: str = typer.Option(..., "--buy-currency", help="Currency to buy (e.g. USD)"),
    buy_amount: str = typer.Option(..., "--buy-amount", help="Amount to buy", callback=decimal_amount),
    sell_account: str = typer.Option(..., "--sell-account", help="Sell account ID"),
    buy_account: str = typer.Option(..., "--buy-account", help="Buy account ID"),
    date: str = typer.Option(..., "--date", help="Conversion date (YYYY-MM-DD)"),
    provider: Optional[str] = typer.Option(None, "--provider", help="FX provider (e.g. airwallex, dbs)"),
    reference: Optional[str] = typer.Option(None, "--reference", help="Provider reference number"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Additional notes"),
    bank_tx: Optional[str] = typer.Option(
        None, "--bank-tx",
        help="Bank transaction ID of the deposit the bought currency landed as (e.g. the synced Aspire SGD "
        "deposit); it is reconciled by this conversion so it is not booked twice",
    ),
) -> None:
    """Record an FX conversion. Auto-creates a balanced journal entry.

    Selling a foreign currency/stablecoin for SGD books realised FX gain/loss against
    the sold account's carrying rate (when an FX gain/loss account is set in `acct ledger`).
    """
    payload: dict = {
        "conversion_date": date,
        "sell_currency": sell_currency,
        "sell_amount": sell_amount,
        "buy_currency": buy_currency,
        "buy_amount": buy_amount,
        "sell_account_id": sell_account,
        "buy_account_id": buy_account,
    }
    if provider:
        payload["provider"] = provider
    if reference:
        payload["reference"] = reference
    if notes:
        payload["notes"] = notes
    if bank_tx:
        payload["bank_transaction_id"] = bank_tx

    data = api_post("/api/fx-conversions", json_data=payload)
    print_success(f"FX conversion recorded: {data['id']}")
    print_success(
        f"{data['sell_currency']} {data['sell_amount']} → "
        f"{data['buy_currency']} {data['buy_amount']} @ {data['fx_rate']}"
    )
    if data.get("journal_entry_id"):
        print_success(f"Journal entry created: {data['journal_entry_id']}")
    print_json(data)


@app.command(name="list")
def list_conversions(
    currency: Optional[str] = typer.Option(None, "--currency", help="Filter by currency"),
) -> None:
    """List FX conversions."""
    params: dict = {}
    if currency:
        params["currency"] = currency
    data = api_get("/api/fx-conversions", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "FX Conversions",
        ["ID", "Date", "Sell", "Buy", "Rate", "Provider"],
        [
            [
                c.get("id", "")[:8],
                c.get("conversion_date", ""),
                f"{c.get('sell_currency', '')} {c.get('sell_amount', '')}",
                f"{c.get('buy_currency', '')} {c.get('buy_amount', '')}",
                c.get("fx_rate", ""),
                c.get("provider", "") or "",
            ]
            for c in items
        ],
    )


@app.command()
def show(
    conversion_id: str = typer.Argument(..., help="FX conversion ID"),
) -> None:
    """Show FX conversion details."""
    data = api_get(f"/api/fx-conversions/{conversion_id}")
    print_json(data)
