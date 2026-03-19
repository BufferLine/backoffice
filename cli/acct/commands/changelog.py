from typing import Optional

import typer

from acct.api_client import api_get
from acct.formatters import print_json, print_table

app = typer.Typer(help="Change log queries")


@app.command()
def history(
    entity_type: str = typer.Argument(..., help="Entity type (e.g. employee, invoice)"),
    entity_id: str = typer.Argument(..., help="Entity UUID"),
    field: Optional[str] = typer.Option(None, "--field", help="Filter by field name"),
) -> None:
    """Show change history for an entity."""
    if field:
        data = api_get(f"/api/changelog/{entity_type}/{entity_id}/{field}")
    else:
        data = api_get(f"/api/changelog/{entity_type}/{entity_id}")
    items = data.get("items", [])
    if not items:
        typer.echo("No change logs found.")
        return
    cols = ["field_name", "old_value", "new_value", "changed_by", "created_at"]
    print_table(
        "Change History",
        cols,
        [[str(item.get(c, "")) for c in cols] for item in items],
    )


@app.command()
def period(
    start_date: str = typer.Argument(..., help="Start date (YYYY-MM-DD)"),
    end_date: str = typer.Argument(..., help="End date (YYYY-MM-DD)"),
    entity_type: Optional[str] = typer.Option(None, "--entity-type", help="Filter by entity type"),
) -> None:
    """Show all changes in a date range."""
    params = {}
    if entity_type:
        params["entity_type"] = entity_type
    data = api_get(f"/api/changelog/period/{start_date}/{end_date}", params=params)
    items = data.get("items", [])
    if not items:
        typer.echo("No change logs found.")
        return
    cols = ["entity_type", "entity_id", "field_name", "old_value", "new_value", "created_at"]
    print_table(
        "Change Log",
        cols,
        [[str(item.get(c, "")) for c in cols] for item in items],
    )
