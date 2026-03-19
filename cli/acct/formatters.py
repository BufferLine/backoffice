import json
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def print_table(title: str, columns: list[str], rows: list[list[Any]]) -> None:
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(v) for v in row])
    console.print(table)


def print_json(data: dict) -> None:
    console.print_json(json.dumps(data, indent=2, default=str))


def print_success(msg: str) -> None:
    console.print(f"[green]{msg}[/green]")


def print_error(msg: str) -> None:
    console.print(f"[red]{msg}[/red]")
