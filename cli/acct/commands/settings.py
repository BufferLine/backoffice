from typing import Optional

import typer

from acct.api_client import api_get, api_patch, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="System settings commands")

# currency_app is exported for registration as a top-level "currency" command in main.py
currency_app = typer.Typer(help="Currency management commands")


@app.command()
def show() -> None:
    """Show current system settings."""
    data = api_get("/api/settings/company")
    print_json(data)


@app.command()
def update(
    company_name: Optional[str] = typer.Option(None, "--company-name", help="Company legal name"),
    uen: Optional[str] = typer.Option(None, "--uen", help="UEN (Unique Entity Number)"),
    default_currency: Optional[str] = typer.Option(
        None, "--default-currency", help="Default currency code"
    ),
) -> None:
    """Update system settings."""
    payload: dict = {}
    if company_name is not None:
        payload["legal_name"] = company_name
    if uen is not None:
        payload["uen"] = uen
    if default_currency is not None:
        payload["default_currency"] = default_currency
    data = api_patch("/api/settings/company", json_data=payload)
    print_success("Settings updated")
    print_json(data)


@app.command()
def upload_logo(filepath: str = typer.Argument(..., help="Path to logo image file")) -> None:
    """Upload company logo image."""
    with open(filepath, "rb") as f:
        files = {"file": (filepath.split("/")[-1], f, "image/png")}
        resp = api_post("/api/settings/company/logo", files=files)
    print_success(f"Logo uploaded: {resp.get('logo_file_id')}")


@app.command()
def upload_stamp(filepath: str = typer.Argument(..., help="Path to stamp image file")) -> None:
    """Upload company stamp/chop image."""
    with open(filepath, "rb") as f:
        files = {"file": (filepath.split("/")[-1], f, "image/png")}
        resp = api_post("/api/settings/company/stamp", files=files)
    print_success(f"Stamp uploaded: {resp.get('stamp_file_id')}")


@currency_app.command(name="add")
def currency_add(
    code: str = typer.Option(..., "--code", help="Currency code (e.g. EUR)"),
    name: str = typer.Option(..., "--name", help="Currency name (e.g. Euro)"),
    symbol: str = typer.Option(..., "--symbol", help="Currency symbol (e.g. €)"),
    precision: int = typer.Option(2, "--precision", help="Decimal precision"),
) -> None:
    """Add a new supported currency."""
    data = api_post(
        "/api/settings/currencies",
        json_data={"code": code, "name": name, "symbol": symbol, "display_precision": precision},
    )
    print_success(f"Currency added: {code}")
    print_json(data)


@currency_app.command(name="list")
def currency_list() -> None:
    """List all supported currencies."""
    data = api_get("/api/settings/currencies")
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Currencies",
        ["Code", "Name", "Symbol", "Precision"],
        [
            [
                c.get("code", ""),
                c.get("name", ""),
                c.get("symbol", ""),
                c.get("display_precision", ""),
            ]
            for c in items
        ],
    )
