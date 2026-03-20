from typing import Optional

import typer

from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Integration provider commands")


@app.command("list")
def list_integrations() -> None:
    """Show configured integration providers."""
    data = api_get("/api/integrations")
    providers = data.get("providers", [])
    print_table(
        "Integration Providers",
        ["Name", "Display Name", "Capabilities", "Configured"],
        [
            [
                p.get("name", ""),
                p.get("display_name", ""),
                ", ".join(p.get("capabilities", [])),
                "yes" if p.get("configured") else "no",
            ]
            for p in providers
        ],
    )


@app.command()
def test(
    provider: str = typer.Argument(..., help="Provider name, e.g. airwallex"),
) -> None:
    """Test connection to an integration provider."""
    data = api_post(f"/api/integrations/{provider}/test")
    status = data.get("status", "unknown")
    if status == "ok":
        print_success(f"Connection to {provider} is healthy")
    else:
        typer.echo(f"Connection status: {status}", err=True)
    print_json(data)


@app.command()
def sync(
    provider: str = typer.Argument(..., help="Provider name, e.g. airwallex"),
    capability: str = typer.Option(
        "sync_transactions",
        "--capability",
        help="Capability to sync: sync_transactions|sync_balance",
    ),
) -> None:
    """Trigger a manual sync for an integration provider."""
    data = api_post(
        f"/api/integrations/{provider}/sync",
        json_data={"capability": capability},
    )
    inserted = data.get("inserted", 0)
    skipped = data.get("skipped", 0)
    errors = data.get("errors", 0)
    print_success(
        f"Sync complete: inserted={inserted} skipped={skipped} errors={errors}"
    )
    print_json(data)


@app.command()
def events(
    provider: str = typer.Argument(..., help="Provider name, e.g. airwallex"),
    limit: int = typer.Option(20, "--limit", help="Number of events to display"),
) -> None:
    """View recent integration events for a provider."""
    data = api_get(f"/api/integrations/{provider}/events", params={"per_page": limit})
    items = data.get("items", [])
    print_table(
        f"Integration Events — {provider}",
        ["ID", "Direction", "Event Type", "Status", "Created At", "Error"],
        [
            [
                str(e.get("id", ""))[:8] + "...",
                e.get("direction", ""),
                e.get("event_type", ""),
                e.get("status", ""),
                e.get("created_at", ""),
                e.get("error_message", "") or "",
            ]
            for e in items
        ],
    )
    total = data.get("total", 0)
    typer.echo(f"Showing {len(items)} of {total} events")
