from typing import Optional

import typer

from acct.api_client import api_get, api_patch, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Account management commands")


@app.command(name="list")
def list_accounts(
    page: int = typer.Option(1, "--page", help="Page number"),
    per_page: int = typer.Option(20, "--per-page", help="Items per page"),
) -> None:
    """List all accounts."""
    params: dict = {"page": page, "per_page": per_page}
    data = api_get("/api/accounts", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Accounts",
        ["ID", "Name", "Type", "Currency", "Institution", "Active"],
        [
            [
                a.get("id", ""),
                a.get("name", ""),
                a.get("account_type", ""),
                a.get("currency", ""),
                a.get("institution", ""),
                str(a.get("is_active", "")),
            ]
            for a in items
        ],
    )


@app.command()
def show(
    account_id: str = typer.Argument(..., help="Account ID"),
) -> None:
    """Show account details."""
    data = api_get(f"/api/accounts/{account_id}")
    print_json(data)


@app.command()
def create(
    name: str = typer.Option(..., "--name", help="Account name"),
    account_type: str = typer.Option(..., "--type", help="Account type: bank|crypto_wallet|cash|virtual"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    institution: Optional[str] = typer.Option(None, "--institution", help="Institution name"),
    account_number: Optional[str] = typer.Option(None, "--account-number", help="Account number"),
    wallet_address: Optional[str] = typer.Option(None, "--wallet-address", help="Wallet address"),
    opening_balance: float = typer.Option(0.0, "--opening-balance", help="Opening balance"),
    opening_balance_date: str = typer.Option(..., "--opening-balance-date", help="Opening balance date (YYYY-MM-DD)"),
) -> None:
    """Create a new account."""
    payload: dict = {
        "name": name,
        "account_type": account_type,
        "currency": currency,
        "opening_balance": str(opening_balance),
        "opening_balance_date": opening_balance_date,
    }
    if institution:
        payload["institution"] = institution
    if account_number:
        payload["account_number"] = account_number
    if wallet_address:
        payload["wallet_address"] = wallet_address
    data = api_post("/api/accounts", json_data=payload)
    print_success(f"Account created: {data['id']}")
    print_json(data)


@app.command()
def balance(
    account_id: str = typer.Argument(..., help="Account ID"),
) -> None:
    """Show account balance breakdown."""
    data = api_get(f"/api/accounts/{account_id}/balance")
    print_json(data)
