from typing import Optional

import typer

from acct.api_client import api_delete, api_get, api_patch, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Payment method management")


@app.command()
def add(
    name: str = typer.Option(..., "--name", help="Payment method name"),
    nickname: Optional[str] = typer.Option(None, "--nickname", help="Human-friendly label"),
    type: str = typer.Option(..., "--type", help="bank_transfer, crypto, paynow"),
    currency: str = typer.Option(..., "--currency", help="Currency code"),
    bank_name: Optional[str] = typer.Option(None, "--bank-name", help="Bank name"),
    bank_account: Optional[str] = typer.Option(None, "--bank-account", help="Bank account number"),
    bank_swift: Optional[str] = typer.Option(None, "--bank-swift", help="SWIFT/BIC code"),
    wallet: Optional[str] = typer.Option(None, "--wallet", help="Wallet address"),
    chain: Optional[str] = typer.Option(None, "--chain", help="Chain ID"),
    uen: Optional[str] = typer.Option(None, "--uen", help="PayNow UEN number"),
    default: bool = typer.Option(False, "--default", help="Set as default for this currency"),
) -> None:
    """Register a payment method."""
    payload: dict = {
        "name": name,
        "type": type,
        "currency": currency,
        "is_default": default,
    }
    if nickname is not None:
        payload["nickname"] = nickname
    if bank_name is not None:
        payload["bank_name"] = bank_name
    if bank_account is not None:
        payload["bank_account_number"] = bank_account
    if bank_swift is not None:
        payload["bank_swift_code"] = bank_swift
    if wallet is not None:
        payload["wallet_address"] = wallet
    if chain is not None:
        payload["chain_id"] = chain
    if uen is not None:
        payload["uen_number"] = uen

    data = api_post("/api/payment-methods", json_data=payload)
    print_success(f"Payment method created: {data['id']}")
    print_json(data)


@app.command(name="list")
def list_methods() -> None:
    """List payment methods."""
    data = api_get("/api/payment-methods")
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Payment Methods",
        ["ID", "Name", "Nickname", "Type", "Currency", "Default", "Active"],
        [
            [
                m.get("id", ""),
                m.get("name", ""),
                m.get("nickname", "") or "",
                m.get("type", ""),
                m.get("currency", ""),
                "yes" if m.get("is_default") else "no",
                "yes" if m.get("is_active") else "no",
            ]
            for m in items
        ],
    )


@app.command()
def show(method_id: str = typer.Argument(..., help="Payment method ID")) -> None:
    """Show payment method details."""
    data = api_get(f"/api/payment-methods/{method_id}")
    print_json(data)


@app.command()
def update(
    method_id: str = typer.Argument(..., help="Payment method ID"),
    name: Optional[str] = typer.Option(None, "--name"),
    nickname: Optional[str] = typer.Option(None, "--nickname"),
    type: Optional[str] = typer.Option(None, "--type"),
    currency: Optional[str] = typer.Option(None, "--currency"),
    bank_name: Optional[str] = typer.Option(None, "--bank-name"),
    bank_account: Optional[str] = typer.Option(None, "--bank-account"),
    bank_swift: Optional[str] = typer.Option(None, "--bank-swift"),
    wallet: Optional[str] = typer.Option(None, "--wallet"),
    chain: Optional[str] = typer.Option(None, "--chain"),
    uen: Optional[str] = typer.Option(None, "--uen"),
    default: Optional[bool] = typer.Option(None, "--default"),
) -> None:
    """Update a payment method."""
    field_map = {
        "name": name, "nickname": nickname, "type": type, "currency": currency,
        "bank_name": bank_name, "bank_account_number": bank_account,
        "bank_swift_code": bank_swift, "wallet_address": wallet,
        "chain_id": chain, "uen_number": uen, "is_default": default,
    }
    payload = {k: v for k, v in field_map.items() if v is not None}
    if not payload:
        typer.echo("No options provided. Use --help to see available options.")
        raise typer.Exit(1)
    data = api_patch(f"/api/payment-methods/{method_id}", json_data=payload)
    print_success("Payment method updated")
    print_json(data)


@app.command()
def deactivate(method_id: str = typer.Argument(..., help="Payment method ID")) -> None:
    """Deactivate a payment method."""
    api_delete(f"/api/payment-methods/{method_id}")
    print_success(f"Payment method {method_id} deactivated")
