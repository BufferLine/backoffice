from typing import Optional

import typer

from acct.api_client import api_post
from acct.formatters import print_json, print_success

app = typer.Typer(help="Automation trigger commands")


@app.command()
def daily() -> None:
    """Run daily automation tasks (overdue checks, reminders)."""
    data = api_post("/api/automation/daily")
    print_success("Daily automation triggered")
    print_json(data)


@app.command()
def weekly() -> None:
    """Run weekly automation tasks (weekly summaries, reports)."""
    data = api_post("/api/automation/weekly")
    print_success("Weekly automation triggered")
    print_json(data)


@app.command()
def monthly(
    month: str = typer.Option(..., "--month", help="Month to process (YYYY-MM)"),
) -> None:
    """Run monthly automation tasks (payroll prep, export generation)."""
    data = api_post("/api/automation/monthly", json_data={"month": month})
    print_success(f"Monthly automation triggered for {month}")
    print_json(data)
