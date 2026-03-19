from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Payroll run commands")


@app.command()
def run(
    employee: str = typer.Option(..., "--employee", help="Employee ID"),
    month: str = typer.Option(..., "--month", help="Payroll month (YYYY-MM)"),
    start_date: Optional[str] = typer.Option(
        None, "--start-date", help="Proration start date (YYYY-MM-DD)"
    ),
) -> None:
    """Create a payroll run for an employee."""
    payload: dict = {"employee_id": employee, "month": month}
    if start_date:
        payload["start_date"] = start_date
    data = api_post("/api/payroll", json_data=payload)
    print_success(f"Payroll run created: {data['id']}")
    print_json(data)


@app.command()
def review(
    payroll_id: str = typer.Argument(..., help="Payroll run ID"),
) -> None:
    """Review a payroll run."""
    data = api_post(f"/api/payroll/{payroll_id}/review")
    print_success(f"Payroll run {payroll_id} marked as reviewed")
    print_json(data)


@app.command()
def finalize(
    payroll_id: str = typer.Argument(..., help="Payroll run ID"),
) -> None:
    """Finalize a payroll run."""
    data = api_post(f"/api/payroll/{payroll_id}/finalize")
    print_success(f"Payroll run {payroll_id} finalized")
    print_json(data)


@app.command()
def mark_paid(
    payroll_id: str = typer.Argument(..., help="Payroll run ID"),
    payment_id: str = typer.Option(..., "--payment-id", help="Payment ID"),
) -> None:
    """Mark a payroll run as paid."""
    data = api_post(
        f"/api/payroll/{payroll_id}/mark-paid",
        json_data={"payment_id": payment_id},
    )
    print_success(f"Payroll run {payroll_id} marked as paid")
    print_json(data)


@app.command(name="list")
def list_payroll(
    month: Optional[str] = typer.Option(None, "--month", help="Filter by month (YYYY-MM)"),
) -> None:
    """List payroll runs."""
    params: dict = {}
    if month:
        params["month"] = month
    data = api_get("/api/payroll", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Payroll Runs",
        ["ID", "Employee", "Month", "Gross", "Net", "Status"],
        [
            [
                run.get("id", ""),
                run.get("employee_id", ""),
                run.get("month", ""),
                run.get("gross_pay", ""),
                run.get("net_pay", ""),
                run.get("status", ""),
            ]
            for run in items
        ],
    )


@app.command()
def show(
    payroll_id: str = typer.Argument(..., help="Payroll run ID"),
) -> None:
    """Show payroll run details."""
    data = api_get(f"/api/payroll/{payroll_id}")
    print_json(data)
