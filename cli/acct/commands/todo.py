from datetime import datetime
from typing import Optional

import typer

from acct.api_client import api_get, api_patch, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Task/todo management")


def _current_period() -> str:
    return datetime.now().strftime("%Y-%m")


@app.command(name="list")
def list_tasks(
    period: Optional[str] = typer.Option(None, "--period", help="Filter by period (e.g. 2026-03)"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category"),
) -> None:
    """List tasks. Defaults to current month."""
    params: dict = {}
    if period:
        params["period"] = period
    else:
        params["period"] = _current_period()
    if status:
        params["status"] = status
    if category:
        params["category"] = category
    data = api_get("/api/tasks", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Tasks",
        ["ID", "Title", "Category", "Priority", "Status", "Due Date", "Period"],
        [
            [
                t.get("id", ""),
                t.get("title", ""),
                t.get("category", ""),
                t.get("priority", ""),
                t.get("status", ""),
                t.get("due_date", ""),
                t.get("period", ""),
            ]
            for t in items
        ],
    )


@app.command()
def summary(
    period: Optional[str] = typer.Option(None, "--period", help="Period (e.g. 2026-03, 2026-Q1, 2026)"),
) -> None:
    """Show todo summary for a period."""
    if period:
        data = api_get(f"/api/tasks/todo/{period}")
    else:
        data = api_get("/api/tasks/todo")
    typer.echo(f"\nPeriod: {data.get('period', '')}")
    typer.echo(f"  Pending:     {data.get('pending', 0)}")
    typer.echo(f"  In Progress: {data.get('in_progress', 0)}")
    typer.echo(f"  Completed:   {data.get('completed', 0)}")
    typer.echo(f"  Overdue:     {data.get('overdue', 0)}")


@app.command()
def complete(
    task_id: str = typer.Argument(..., help="Task instance ID"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Completion notes"),
) -> None:
    """Mark a task as completed."""
    params: dict = {}
    if notes:
        params["notes"] = notes
    data = api_post(f"/api/tasks/{task_id}/complete", params=params)
    print_success(f"Task {task_id} marked as completed")
    print_json(data)


@app.command()
def skip(
    task_id: str = typer.Argument(..., help="Task instance ID"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Skip reason"),
) -> None:
    """Skip a task."""
    params: dict = {}
    if notes:
        params["notes"] = notes
    data = api_post(f"/api/tasks/{task_id}/skip", params=params)
    print_success(f"Task {task_id} skipped")
    print_json(data)


@app.command()
def add(
    title: str = typer.Argument(..., help="Task title"),
    description: Optional[str] = typer.Option(None, "--description", help="Task description"),
    category: str = typer.Option("custom", "--category", help="Category"),
    priority: str = typer.Option("medium", "--priority", help="Priority: high/medium/low"),
    due_date: Optional[str] = typer.Option(None, "--due-date", help="Due date (YYYY-MM-DD)"),
    period: Optional[str] = typer.Option(None, "--period", help="Period (e.g. 2026-03)"),
) -> None:
    """Create an ad-hoc task."""
    payload: dict = {
        "title": title,
        "category": category,
        "priority": priority,
    }
    if description:
        payload["description"] = description
    if due_date:
        payload["due_date"] = due_date
    if period:
        payload["period"] = period
    data = api_post("/api/tasks", json_data=payload)
    print_success(f"Task created: {data['id']}")
    print_json(data)


@app.command()
def generate(
    since: Optional[str] = typer.Option(None, "--since", help="Backfill from this month (YYYY-MM) to now"),
) -> None:
    """Generate task instances from templates. Use --since to backfill missed periods."""
    params: dict = {}
    if since:
        params["since"] = since
    data = api_post("/api/tasks/generate", params=params)
    count = data.get("generated", 0)
    items = data.get("items", [])
    if count > 0:
        print_success(f"{count} task(s) generated")
        for item in items:
            typer.echo(f"  {item.get('period', '')} — {item.get('title', '')}")
    else:
        typer.echo("No new tasks to generate (all up to date)")


@app.command()
def archive(
    task_id: str = typer.Argument(..., help="Task instance ID"),
) -> None:
    """Archive a completed/skipped task."""
    data = api_post(f"/api/tasks/{task_id}/archive")
    print_success(f"Task {task_id} archived")
    print_json(data)


@app.command()
def upcoming(
    days: int = typer.Option(30, "--days", help="Number of days ahead"),
) -> None:
    """Show upcoming tasks."""
    data = api_get("/api/tasks/upcoming", params={"days": days})
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        f"Upcoming Tasks (next {days} days)",
        ["ID", "Title", "Category", "Priority", "Status", "Due Date"],
        [
            [
                t.get("id", ""),
                t.get("title", ""),
                t.get("category", ""),
                t.get("priority", ""),
                t.get("status", ""),
                t.get("due_date", ""),
            ]
            for t in items
        ],
    )


@app.command()
def overdue() -> None:
    """Show overdue tasks."""
    data = api_get("/api/tasks/overdue")
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Overdue Tasks",
        ["ID", "Title", "Category", "Priority", "Due Date", "Period"],
        [
            [
                t.get("id", ""),
                t.get("title", ""),
                t.get("category", ""),
                t.get("priority", ""),
                t.get("due_date", ""),
                t.get("period", ""),
            ]
            for t in items
        ],
    )


@app.command()
def note(
    task_id: str = typer.Argument(..., help="Task instance ID"),
    note_text: str = typer.Argument(..., help="Note to add"),
) -> None:
    """Add a note to a task."""
    data = api_post(f"/api/tasks/{task_id}/note", params={"note": note_text})
    print_success(f"Note added to task {task_id}")
    print_json(data)


# ---------------------------------------------------------------------------
# Template management
# ---------------------------------------------------------------------------


@app.command()
def template_add(
    title: str = typer.Argument(..., help="Template title"),
    frequency: str = typer.Option(..., "--frequency", help="Frequency: monthly/quarterly/yearly/once"),
    category: str = typer.Option("custom", "--category", help="Category"),
    due_day: Optional[int] = typer.Option(None, "--due-day", help="Day of month (1-28)"),
    priority: str = typer.Option("medium", "--priority", help="Priority: high/medium/low"),
) -> None:
    """Create a recurring task template."""
    payload: dict = {
        "title": title,
        "frequency": frequency,
        "category": category,
        "priority": priority,
    }
    if due_day is not None:
        payload["due_day"] = due_day
    data = api_post("/api/tasks/templates", json_data=payload)
    print_success(f"Template created: {data['id']}")
    print_json(data)


@app.command()
def template_list(
    category: Optional[str] = typer.Option(None, "--category", help="Filter by category"),
) -> None:
    """List task templates."""
    params: dict = {}
    if category:
        params["category"] = category
    data = api_get("/api/tasks/templates", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Task Templates",
        ["ID", "Title", "Category", "Frequency", "Due Day", "Priority", "System", "Active"],
        [
            [
                t.get("id", ""),
                t.get("title", ""),
                t.get("category", ""),
                t.get("frequency", ""),
                str(t.get("due_day", "")),
                t.get("priority", ""),
                str(t.get("is_system", "")),
                str(t.get("is_active", "")),
            ]
            for t in items
        ],
    )
