from typing import Optional

import typer

from acct.commands import auth, automation, bank, changelog, client, employee, expense, export, invoice, payment, payroll, settings, todo
from acct.commands import account, transaction, commitment
from acct.commands import payment_method
from acct.commands import integration, loan
from acct.commands import journal, report, fx
from acct.api_client import api_post
from acct.config import save_credentials
from acct.formatters import print_success

app = typer.Typer(
    name="acct",
    help="Backoffice Operations CLI\n\n"
    "AI agents: run 'acct guide' first to understand the system and build your own memory/rules.",
)

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
app.add_typer(integration.app, name="integration")
app.add_typer(loan.app, name="loan")
app.add_typer(journal.app, name="journal")
app.add_typer(report.app, name="report")
app.add_typer(fx.app, name="fx")


AGENT_GUIDE = """
=== BACKOFFICE AGENT GUIDE ===

You are operating a Singapore-based backoffice system for invoicing, payroll,
expenses, payments, and double-entry bookkeeping.

## How this system works

1. BANK TRANSACTIONS come in via Airwallex sync or PDF/CSV statement import
2. Each transaction needs to be RECONCILED — matched to the right accounts
3. Reconciliation creates a JOURNAL ENTRY (double-entry: debit + credit)
4. The TRIAL BALANCE shows all accounts are in balance

## Your core workflow

  acct bank tx-list --status unreconciled     # What needs your attention
  acct account list                            # Available accounts
  acct bank tx-reconcile TX_ID \\
    --bank-account ASSET_UUID \\
    --contra-account EXPENSE_UUID              # Create the journal entry
  acct report trial-balance                    # Verify everything balances

## How to classify transactions

Look at the description/counterparty of each bank transaction and decide:
- Is it an expense? Which category? (salary, software, transport, food, etc.)
- Is it revenue? (invoice payment, interest, etc.)
- Is it a transfer between accounts? (loan, capital injection, etc.)

## IMPORTANT: Build your own memory

You SHOULD maintain your own notes/memory about this company's accounts:
- Which account UUIDs map to what (e.g. "Airwallex SGD = uuid:xxx")
- Recurring counterparties and their categories (e.g. "CLAUDE.AI → software expense")
- Classification rules you've learned from past decisions

When you encounter a transaction you're unsure about, ASK the user.
When the user corrects you, REMEMBER that correction for next time.

Over time you should need to ask less and less.

## Key commands by area

  Bookkeeping:  acct journal create|list|confirm|delete
  Reports:      acct report trial-balance
  Bank:         acct bank statement-upload|tx-list|tx-reconcile|tx-auto-match
  Invoicing:    acct invoice create|list|issue|mark-paid
  Payroll:      acct payroll create|review|finalize|mark-paid
  Expenses:     acct expense create|list|confirm|reimburse
  Payments:     acct payment record|list|link
  FX:           acct fx record|list|show
  Accounts:     acct account create|list|balance

## Double-entry basics

Every journal entry has balanced debit and credit lines:
- DEPOSIT to bank:   debit asset(bank), credit revenue/liability
- WITHDRAWAL:        debit expense/asset, credit asset(bank)
- Asset/Expense accounts: balance = debits - credits (debit-normal)
- Liability/Equity/Revenue accounts: balance = credits - debits (credit-normal)

Run 'acct <command> --help' for detailed usage of any command.
"""


@app.command()
def guide() -> None:
    """Print agent guide — read this first if you're an AI agent operating this system."""
    typer.echo(AGENT_GUIDE)


@app.command()
def init(
    company_name: str = typer.Option(None, "--company-name", help="Company legal name"),
    jurisdiction: str = typer.Option(None, "--jurisdiction", help="Jurisdiction code (SG, KR, etc.)"),
    uen: str = typer.Option(None, "--uen", help="Company UEN (optional)"),
    admin_email: str = typer.Option(None, "--admin-email", help="Admin email (skips browser setup)"),
    admin_password: str = typer.Option(None, "--admin-password", help="Admin password"),
    admin_name: str = typer.Option(None, "--admin-name", help="Admin display name"),
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
    token = setup_url.split("token=")[-1]
    print_success("System initialized!")

    if admin_email:
        # Direct admin creation (skip browser)
        if not admin_password:
            admin_password = typer.prompt("Admin password", hide_input=True)
        if not admin_name:
            admin_name = typer.prompt("Admin name", default="Admin")

        complete_resp = api_post(
            "/api/setup/complete",
            json_data={
                "token": token,
                "email": admin_email,
                "password": admin_password,
                "name": admin_name,
            },
        )
        # Auto-login with the returned token
        access_token = complete_resp.get("access_token", "")
        save_credentials(access_token, api_url)
        print_success(f"Admin account created and logged in as {admin_email}")
    else:
        typer.echo(f"\nOpen this link in your browser to create your admin account:\n")
        typer.echo(f"  {setup_url}\n")
        typer.echo("This link expires in 1 hour and can only be used once.")


@app.command()
def login(
    email: str = typer.Option(None, help="Email address"),
    password: str = typer.Option(None, help="Password", hide_input=True),
    token: str = typer.Option(None, help="API token (alternative to email/password)"),
    api_url: str = typer.Option("http://localhost:8000", help="API base URL"),
) -> None:
    """Login to the backoffice system."""
    auth.login(email=email, password=password, token=token, api_url=api_url)


@app.command()
def logout() -> None:
    """Logout from the backoffice system."""
    auth.logout()


@app.command()
def whoami() -> None:
    """Show current user info."""
    auth.whoami()
