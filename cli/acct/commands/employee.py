from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Employee management commands")


@app.command()
def add(
    name: str = typer.Option(..., "--name", help="Employee full name"),
    salary: float = typer.Option(..., "--salary", help="Monthly salary amount"),
    currency: str = typer.Option("SGD", "--currency", help="Salary currency code"),
    start_date: str = typer.Option(..., "--start-date", help="Employment start date (YYYY-MM-DD)"),
    pass_type: str = typer.Option("EP", "--pass-type", help="Work pass type (EP, SP, WP, PR, Citizen)"),
) -> None:
    """Add a new employee."""
    data = api_post(
        "/api/employees",
        json_data={
            "name": name,
            "base_salary": str(salary),
            "salary_currency": currency,
            "start_date": start_date,
            "work_pass_type": pass_type,
            "tax_residency": "SG",
        },
    )
    print_success(f"Employee added: {data['id']}")
    print_json(data)


@app.command(name="list")
def list_employees() -> None:
    """List all employees."""
    data = api_get("/api/employees")
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Employees",
        ["ID", "Name", "Salary", "Currency", "Pass Type", "Start Date", "Status"],
        [
            [
                emp.get("id", "")[:8],
                emp.get("name", ""),
                emp.get("base_salary", ""),
                emp.get("salary_currency", ""),
                emp.get("work_pass_type", ""),
                emp.get("start_date", ""),
                emp.get("status", ""),
            ]
            for emp in items
        ],
    )


@app.command()
def show(
    employee_id: str = typer.Argument(..., help="Employee ID"),
) -> None:
    """Show employee details."""
    data = api_get(f"/api/employees/{employee_id}")
    print_json(data)
