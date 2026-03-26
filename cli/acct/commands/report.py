from typing import Optional

import typer

from acct.api_client import api_get
from acct.formatters import print_table

app = typer.Typer(help="Financial reports")


@app.command("trial-balance")
def trial_balance(
    as_of: Optional[str] = typer.Option(None, "--date", help="As of date (YYYY-MM-DD)"),
    include_unconfirmed: bool = typer.Option(False, "--include-unconfirmed", help="Include unconfirmed entries"),
) -> None:
    """Show trial balance (sum of debits and credits per account)."""
    params: dict = {}
    if as_of:
        params["as_of"] = as_of
    if include_unconfirmed:
        params["confirmed_only"] = "false"

    data = api_get("/api/journal-entries/trial-balance", params=params)
    rows = data.get("rows", [])

    print_table(
        f"Trial Balance as of {data.get('as_of', 'today')}",
        ["Account", "Class", "Currency", "Debit", "Credit", "Balance"],
        [
            [
                r.get("account_name", ""),
                r.get("account_class") or "-",
                r.get("currency", ""),
                r.get("total_debit", "0"),
                r.get("total_credit", "0"),
                r.get("balance", "0"),
            ]
            for r in rows
        ],
    )

    total_d = data.get("total_debit", "0")
    total_c = data.get("total_credit", "0")
    balanced = data.get("is_balanced", False)
    typer.echo(f"\nTotal Debit: {total_d}  |  Total Credit: {total_c}  |  Balanced: {'Yes' if balanced else 'NO'}")
