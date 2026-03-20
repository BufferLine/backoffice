from typing import Optional

import typer

from acct.api_client import api_download, api_get, api_patch, api_post, get_client, resolve_payroll_id
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
    payload: dict = {"employee_id": employee, "month": f"{month}-01"}
    if start_date:
        payload["start_date"] = start_date
    data = api_post("/api/payroll/runs", json_data=payload)
    print_success(f"Payroll run created: {data['id']}")
    print_json(data)


@app.command()
def review(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
) -> None:
    """Review a payroll run."""
    payroll_id = resolve_payroll_id(payroll_id)
    data = api_post(f"/api/payroll/runs/{payroll_id}/review")
    print_success(f"Payroll run reviewed")
    print_json(data)


@app.command()
def finalize(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
) -> None:
    """Finalize a payroll run."""
    payroll_id = resolve_payroll_id(payroll_id)
    data = api_post(f"/api/payroll/runs/{payroll_id}/finalize")
    print_success(f"Payroll run finalized")
    print_json(data)


@app.command()
def mark_paid(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
    payment_id: str = typer.Option(..., "--payment-id", help="Payment ID"),
) -> None:
    """Mark a payroll run as paid."""
    payroll_id = resolve_payroll_id(payroll_id)
    data = api_post(
        f"/api/payroll/runs/{payroll_id}/mark-paid",
        json_data={"payment_id": payment_id},
    )
    print_success(f"Payroll run marked as paid")
    print_json(data)


@app.command(name="list")
def list_payroll(
    month: Optional[str] = typer.Option(None, "--month", help="Filter by month (YYYY-MM)"),
) -> None:
    """List payroll runs."""
    params: dict = {}
    if month:
        params["month"] = month
    data = api_get("/api/payroll/runs", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Payroll Runs",
        ["ID", "Employee", "Month", "Prorated", "Deductions", "Net", "Status"],
        [
            [
                r.get("id", ""),
                r.get("employee_id", ""),
                r.get("month", ""),
                r.get("prorated_gross_salary", ""),
                r.get("total_deductions", ""),
                r.get("net_salary", ""),
                r.get("status", ""),
            ]
            for r in items
        ],
    )


@app.command()
def show(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
) -> None:
    """Show payroll run details."""
    payroll_id = resolve_payroll_id(payroll_id)
    data = api_get(f"/api/payroll/runs/{payroll_id}")
    print_json(data)


@app.command()
def download(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
    output: str = typer.Option(".", "-o", "--output", help="Output directory or file path"),
) -> None:
    """Download payslip PDF."""
    payroll_id = resolve_payroll_id(payroll_id)
    filepath = api_download(f"/api/payroll/runs/{payroll_id}/pdf", output)
    print_success(f"Downloaded: {filepath}")


@app.command()
def delete(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
    reason: Optional[str] = typer.Option(None, "--reason", help="Reason for deletion (required for finalized runs)"),
) -> None:
    """Delete a payroll run."""
    payroll_id = resolve_payroll_id(payroll_id)
    params: dict = {}
    if reason:
        params["reason"] = reason
    with get_client() as client:
        resp = client.delete(f"/api/payroll/runs/{payroll_id}", params=params)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            typer.echo(f"Error {resp.status_code}: {detail}", err=True)
            raise typer.Exit(1)
    print_success(f"Payroll run {payroll_id} deleted")


@app.command()
def edit(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="New start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end-date", help="New end date (YYYY-MM-DD)"),
) -> None:
    """Edit a draft payroll run (recalculates proration)."""
    payroll_id = resolve_payroll_id(payroll_id)
    payload: dict = {}
    if start_date is not None:
        payload["start_date"] = start_date
    if end_date is not None:
        payload["end_date"] = end_date
    data = api_patch(f"/api/payroll/runs/{payroll_id}", json_data=payload)
    print_success(f"Payroll run {payroll_id} updated")
    print_json(data)


@app.command()
def regenerate_pdf(
    payroll_id: str = typer.Argument(..., help="Payroll run ID (prefix ok)"),
) -> None:
    """Regenerate payslip PDF with current company branding."""
    payroll_id = resolve_payroll_id(payroll_id)
    data = api_post(f"/api/payroll/runs/{payroll_id}/regenerate-pdf")
    print_success(f"Payslip PDF regenerated for payroll run {payroll_id}")
    print_json(data)
