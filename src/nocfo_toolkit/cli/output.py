"""Output formatting helpers for CLI."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from nocfo_toolkit.config import OutputFormat

console = Console()

_MAX_TABLE_COLUMNS = 10


def print_data(
    data: Any,
    output_format: OutputFormat = OutputFormat.TABLE,
    *,
    columns: Sequence[str] | None = None,
) -> None:
    """Render data as JSON or a table-like output."""

    if output_format == OutputFormat.JSON:
        console.print_json(data=json.dumps(data, default=str))
        return

    if isinstance(data, list):
        _print_list(data, columns=columns)
        return

    if isinstance(data, dict):
        _print_dict(data)
        return

    console.print(str(data))


def print_error(message: str) -> None:
    """Render a styled error message."""

    console.print(f"[red]Error:[/red] {message}")


def _print_dict(data: dict[str, Any]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Field")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(str(key), _value_to_text(value))
    console.print(table)


def _print_list(
    items: list[Any],
    *,
    columns: Sequence[str] | None = None,
) -> None:
    if not items:
        console.print("No results.")
        return

    if all(isinstance(item, dict) for item in items):
        all_keys = sorted({key for item in items for key in item.keys()})

        if columns:
            keys = [k for k in columns if k in all_keys]
        else:
            keys = all_keys

        total = len(all_keys)
        truncated = len(keys) > _MAX_TABLE_COLUMNS
        if truncated:
            keys = keys[:_MAX_TABLE_COLUMNS]

        table = Table(show_header=True, header_style="bold")
        for key in keys:
            table.add_column(str(key))
        for item in items:
            table.add_row(*[_value_to_text(item.get(key)) for key in keys])
        console.print(table)

        if truncated:
            console.print(
                Text(
                    f"Showing {len(keys)} of {total} fields. "
                    "Use --output json to see all.",
                    style="dim",
                )
            )
        return

    for item in items:
        console.print(_value_to_text(item))


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) > 60:
            return text[:57] + "..."
        return text
    return str(value)
