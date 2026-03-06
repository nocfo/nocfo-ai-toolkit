"""Schema introspection commands."""

from __future__ import annotations

from typing import Any

import typer

from nocfo_toolkit.cli.context import get_context
from nocfo_toolkit.cli.output import print_data
from nocfo_toolkit.openapi import filter_mcp_spec, load_openapi_spec

app = typer.Typer(help="Inspect OpenAPI schema used by CLI and MCP.")


@app.command("list")
def list_operations(
    ctx: typer.Context,
    mcp_only: bool = typer.Option(
        True,
        "--mcp-only/--all",
        help="Show only MCP-tagged operations by default.",
    ),
) -> None:
    command_ctx = get_context(ctx)
    spec = load_openapi_spec(base_url=command_ctx.config.base_url)
    if mcp_only:
        spec = filter_mcp_spec(spec, mcp_tag="MCP")

    operations: list[dict[str, Any]] = []
    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, meta in methods.items():
            if not isinstance(meta, dict):
                continue
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": meta.get("operationId"),
                    "summary": meta.get("summary"),
                    "tags": meta.get("tags", []),
                }
            )

    operations.sort(key=lambda item: (item["path"], item["method"]))
    print_data(operations, command_ctx.config.output_format)


@app.command("show")
def show_operation(
    ctx: typer.Context,
    query: str,
    mcp_only: bool = typer.Option(
        True,
        "--mcp-only/--all",
        help="Search only MCP-tagged operations by default.",
    ),
) -> None:
    command_ctx = get_context(ctx)
    spec = load_openapi_spec(base_url=command_ctx.config.base_url)
    if mcp_only:
        spec = filter_mcp_spec(spec, mcp_tag="MCP")

    normalized_query = query.strip().lower()
    if not normalized_query:
        raise typer.BadParameter("Query cannot be empty.")

    matches: list[dict[str, Any]] = []
    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, meta in methods.items():
            if not isinstance(meta, dict):
                continue
            operation_id = str(meta.get("operationId", ""))
            if (
                normalized_query in path.lower()
                or normalized_query in method.lower()
                or normalized_query in operation_id.lower()
            ):
                matches.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "operation": meta,
                    }
                )

    if not matches:
        raise typer.BadParameter(f"No operation matches query '{query}'.")

    if len(matches) == 1:
        print_data(matches[0], command_ctx.config.output_format)
        return

    print_data(matches, command_ctx.config.output_format)
