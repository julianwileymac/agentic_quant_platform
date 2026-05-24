"""rich-based output helpers (tables, colored info/warn/error, token redaction)."""

from __future__ import annotations

import json
from collections.abc import Iterable

from rich.console import Console
from rich.table import Table

console = Console()


def info(msg: str) -> None:
    console.print(f"[cyan]i[/cyan] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[red]x[/red] {msg}")


def render_table(title: str, columns: Iterable[str], rows: Iterable[list[str]]) -> None:
    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(col, no_wrap=False)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def render_json(payload: object) -> None:
    console.print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def redact_token(token: str) -> str:
    """Return the first 4 chars + ellipsis. Never print full tokens.

    Enforces the always-on credential-safety rule at
    ``.cursor/rules/aqp-management-engine.mdc``.
    """
    if not token:
        return "<empty>"
    if len(token) <= 4:
        return "<redacted>"
    return f"{token[:4]}..."
