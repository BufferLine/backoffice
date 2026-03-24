from typing import Optional

import typer

from acct.api_client import api_download, api_get, api_patch, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Loan management commands")


@app.command()
def create(
    loan_type: str = typer.Option(..., "--type", help="Loan type: shareholder_loan, director_loan, intercompany_loan, third_party_loan"),
    direction: str = typer.Option(..., "--direction", help="Direction: inbound (company borrows) or outbound (company lends)"),
    counterparty: str = typer.Option(..., "--counterparty", help="Counterparty name"),
    principal: float = typer.Option(..., "--principal", help="Principal amount"),
    start_date: str = typer.Option(..., "--start-date", help="Start date (YYYY-MM-DD)"),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    interest_rate: Optional[float] = typer.Option(None, "--interest-rate", help="Annual interest rate (e.g. 0.05 for 5%)"),
    interest_type: str = typer.Option("simple", "--interest-type", help="Interest type: simple or compound"),
    maturity_date: Optional[str] = typer.Option(None, "--maturity-date", help="Maturity date (YYYY-MM-DD)"),
    description: Optional[str] = typer.Option(None, "--description", help="Loan description"),
) -> None:
    """Create a new loan."""
    payload: dict = {
        "loan_type": loan_type,
        "direction": direction,
        "counterparty": counterparty,
        "principal": principal,
        "start_date": start_date,
        "currency": currency,
        "interest_type": interest_type,
    }
    if interest_rate is not None:
        payload["interest_rate"] = interest_rate
    if maturity_date is not None:
        payload["maturity_date"] = maturity_date
    if description is not None:
        payload["description"] = description
    data = api_post("/api/loans", json_data=payload)
    print_success(f"Loan created: {data['id']}")
    print_json(data)


@app.command(name="list")
def list_loans(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status: active, repaid, written_off"),
    loan_type: Optional[str] = typer.Option(None, "--type", help="Filter by loan type"),
) -> None:
    """List loans."""
    params: dict = {}
    if status:
        params["loan_status"] = status
    if loan_type:
        params["loan_type"] = loan_type
    data = api_get("/api/loans", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Loans",
        ["ID", "Type", "Direction", "Counterparty", "Currency", "Principal", "Status"],
        [
            [
                loan.get("id", ""),
                loan.get("loan_type", ""),
                loan.get("direction", ""),
                loan.get("counterparty", ""),
                loan.get("currency", ""),
                loan.get("principal", ""),
                loan.get("status", ""),
            ]
            for loan in items
        ],
    )


@app.command()
def show(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Show loan details."""
    data = api_get(f"/api/loans/{loan_id}")
    print_json(data)


@app.command()
def edit(
    loan_id: str = typer.Argument(..., help="Loan ID"),
    counterparty: Optional[str] = typer.Option(None, "--counterparty", help="Counterparty name"),
    principal: Optional[float] = typer.Option(None, "--principal", help="Principal amount"),
    interest_rate: Optional[float] = typer.Option(None, "--interest-rate", help="Annual interest rate"),
    interest_type: Optional[str] = typer.Option(None, "--interest-type", help="Interest type: simple or compound"),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="Start date (YYYY-MM-DD)"),
    maturity_date: Optional[str] = typer.Option(None, "--maturity-date", help="Maturity date (YYYY-MM-DD)"),
    description: Optional[str] = typer.Option(None, "--description", help="Loan description"),
) -> None:
    """Edit an existing loan."""
    payload: dict = {}
    if counterparty is not None:
        payload["counterparty"] = counterparty
    if principal is not None:
        payload["principal"] = principal
    if interest_rate is not None:
        payload["interest_rate"] = interest_rate
    if interest_type is not None:
        payload["interest_type"] = interest_type
    if start_date is not None:
        payload["start_date"] = start_date
    if maturity_date is not None:
        payload["maturity_date"] = maturity_date
    if description is not None:
        payload["description"] = description
    data = api_patch(f"/api/loans/{loan_id}", json_data=payload)
    print_success(f"Loan {loan_id} updated")
    print_json(data)


@app.command()
def balance(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Show loan balance and repayment allocations."""
    data = api_get(f"/api/loans/{loan_id}/balance")
    print_json(data)


@app.command()
def mark_repaid(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Mark a loan as fully repaid."""
    data = api_post(f"/api/loans/{loan_id}/mark-repaid")
    print_success(f"Loan {loan_id} marked as repaid")
    print_json(data)


@app.command()
def write_off(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Write off a loan."""
    data = api_post(f"/api/loans/{loan_id}/write-off")
    print_success(f"Loan {loan_id} written off")
    print_json(data)


@app.command()
def generate_pdf(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Generate loan agreement PDF."""
    data = api_post(f"/api/loans/{loan_id}/generate-pdf")
    print_success(f"Loan agreement PDF generated: {data.get('document_file_id', '')}")
    print_json(data)


@app.command()
def generate_statement(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Generate loan statement PDF."""
    data = api_post(f"/api/loans/{loan_id}/generate-statement")
    print_success(f"Loan statement PDF generated: {data.get('document_file_id', '')}")
    print_json(data)


@app.command()
def generate_discharge(
    loan_id: str = typer.Argument(..., help="Loan ID"),
) -> None:
    """Generate loan discharge letter PDF."""
    data = api_post(f"/api/loans/{loan_id}/generate-discharge")
    print_success(f"Loan discharge PDF generated: {data.get('document_file_id', '')}")
    print_json(data)


@app.command()
def download(
    loan_id: str = typer.Argument(..., help="Loan ID"),
    doc_type: str = typer.Option("agreement", "--type", help="Document type: agreement, statement, discharge"),
    output: str = typer.Option(".", "-o", "--output", help="Output directory or file path"),
) -> None:
    """Download a loan document PDF."""
    endpoint_map = {
        "agreement": "agreement-pdf",
        "statement": "statement-pdf",
        "discharge": "discharge-pdf",
    }
    endpoint = endpoint_map.get(doc_type)
    if not endpoint:
        typer.echo(f"Unknown document type: {doc_type}. Use: agreement, statement, discharge", err=True)
        raise typer.Exit(1)

    filepath = api_download(f"/api/loans/{loan_id}/{endpoint}", output)
    print_success(f"Downloaded: {filepath}")
