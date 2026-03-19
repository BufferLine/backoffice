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
    address: Optional[str] = typer.Option(None, "--address", help="Company address"),
    billing_email: Optional[str] = typer.Option(None, "--billing-email", help="Billing email"),
    bank_name: Optional[str] = typer.Option(None, "--bank-name", help="Bank name"),
    bank_account: Optional[str] = typer.Option(None, "--bank-account", help="Bank account number"),
    bank_swift: Optional[str] = typer.Option(None, "--bank-swift", help="SWIFT/BIC code"),
    default_currency: Optional[str] = typer.Option(None, "--default-currency", help="Default currency code"),
    payment_terms: Optional[int] = typer.Option(None, "--payment-terms", help="Default payment terms (days)"),
    gst_registered: Optional[bool] = typer.Option(None, "--gst-registered", help="GST registered"),
    gst_rate: Optional[float] = typer.Option(None, "--gst-rate", help="GST rate (e.g. 0.09)"),
    jurisdiction: Optional[str] = typer.Option(None, "--jurisdiction", help="Jurisdiction code (SG, KR)"),
    primary_color: Optional[str] = typer.Option(None, "--primary-color", help="Primary theme color (hex)"),
    accent_color: Optional[str] = typer.Option(None, "--accent-color", help="Accent theme color (hex)"),
    font_family: Optional[str] = typer.Option(None, "--font-family", help="PDF font family"),
) -> None:
    """Update system settings."""
    field_map = {
        "legal_name": company_name,
        "uen": uen,
        "address": address,
        "billing_email": billing_email,
        "bank_name": bank_name,
        "bank_account_number": bank_account,
        "bank_swift_code": bank_swift,
        "default_currency": default_currency,
        "default_payment_terms_days": payment_terms,
        "gst_registered": gst_registered,
        "gst_rate": gst_rate,
        "jurisdiction": jurisdiction,
        "primary_color": primary_color,
        "accent_color": accent_color,
        "font_family": font_family,
    }
    payload = {k: v for k, v in field_map.items() if v is not None}
    if not payload:
        typer.echo("No options provided. Use --help to see available options.")
        raise typer.Exit(1)
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
