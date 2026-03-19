from pathlib import Path
from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Export pack commands")


@app.command()
def validate(
    month: str = typer.Option(..., "--month", help="Month to validate (YYYY-MM)"),
) -> None:
    """Validate data completeness before month-end export."""
    data = api_post(f"/api/exports/validate/{month}")
    print_json(data)


@app.command()
def month_end(
    month: str = typer.Option(..., "--month", help="Month to export (YYYY-MM)"),
    force: bool = typer.Option(False, "--force", help="Force export even with validation warnings"),
) -> None:
    """Run month-end export pack generation."""
    data = api_post("/api/exports/month-end", json_data={"month": month, "force": force})
    print_success(f"Export pack created: {data.get('id', '')}")
    print_json(data)


@app.command(name="list")
def list_exports() -> None:
    """List export packs."""
    data = api_get("/api/exports")
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Export Packs",
        ["ID", "Month", "Status", "Created At"],
        [
            [
                exp.get("id", ""),
                exp.get("month", ""),
                exp.get("status", ""),
                exp.get("created_at", ""),
            ]
            for exp in items
        ],
    )


@app.command()
def download(
    export_id: str = typer.Argument(..., help="Export pack ID"),
    output: Path = typer.Option(
        Path("./exports"), "--output", help="Output directory for downloaded files"
    ),
) -> None:
    """Download an export pack to a local directory."""
    data = api_get(f"/api/exports/{export_id}/download-url")
    download_url = data.get("url", "")
    if not download_url:
        print_json(data)
        return

    import httpx

    output.mkdir(parents=True, exist_ok=True)
    filename = data.get("filename", f"export-{export_id}.zip")
    dest = output / filename
    with httpx.stream("GET", download_url) as resp:
        dest.write_bytes(resp.read())
    print_success(f"Downloaded to {dest}")
