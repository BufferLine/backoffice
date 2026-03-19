import typer

from acct.commands import auth, automation, bank, employee, expense, export, invoice, payment, payroll, settings, todo

app = typer.Typer(name="acct", help="Backoffice Operations CLI")

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
