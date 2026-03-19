from typing import Optional

import typer

from acct.commands import auth, automation, bank, changelog, client, employee, expense, export, invoice, payment, payroll, settings, todo
from acct.commands import account, transaction, commitment
from acct.commands import payment_method
from acct.api_client import api_post
from acct.config import save_credentials
from acct.formatters import print_success

app = typer.Typer(name="acct", help="Backoffice Operations CLI")

app.add_typer(client.app, name="client")
app.add_typer(auth.app, name="auth")
app.add_typer(invoice.app, name="invoice")
app.add_typer(employee.app, name="employee")
app.add_typer(payroll.app, name="payroll")
app.add_typer(expense.app, name="expense")
app.add_typer(payment.app, name="payment")
app.add_typer(export.app, name="export")
app.add_typer(automation.app, name="automation")
app.add_typer(settings.app, name="settings")
app.add_typer(bank.app, name="bank")
app.add_typer(settings.currency_app, name="currency")
app.add_typer(todo.app, name="todo")
app.add_typer(changelog.app, name="changelog")
app.add_typer(account.app, name="account")
app.add_typer(transaction.app, name="transaction")
app.add_typer(commitment.app, name="commitment")
app.add_typer(payment_method.app, name="payment-method")


@app.command()
def init(
    company_name: str = typer.Option(None, "--company-name", help="Company legal name"),
    jurisdiction: str = typer.Option(None, "--jurisdiction", help="Jurisdiction code (SG, KR, etc.)"),
    uen: str = typer.Option(None, "--uen", help="Company UEN (optional)"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
) -> None:
    """Initialize the backoffice system. Options are prompted interactively if not provided."""
    if not company_name:
        company_name = typer.prompt("Company name")
    if not jurisdiction:
        jurisdiction = typer.prompt("Jurisdiction (SG, KR, etc.)", default="SG")
    if uen is None:
        uen = typer.prompt("UEN (optional, press enter to skip)", default="")

    save_credentials("", api_url)
    resp = api_post(
        "/api/setup/init",
        json_data={
            "company_name": company_name,
            "jurisdiction": jurisdiction,
            "uen": uen or None,
        },
    )
    setup_url = resp["setup_url"]
    print_success("System initialized!")
    typer.echo(f"\nOpen this link in your browser to create your admin account:\n")
    typer.echo(f"  {setup_url}\n")
    typer.echo("This link expires in 1 hour and can only be used once.")


@app.command()
def login(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    api_url: str = typer.Option("http://localhost:8000", help="API base URL"),
) -> None:
    """Login to the backoffice system."""
    auth.login(email=email, password=password, api_url=api_url)


@app.command()
def logout() -> None:
    """Logout from the backoffice system."""
    auth.logout()


@app.command()
def whoami() -> None:
    """Show current user info."""
    auth.whoami()
