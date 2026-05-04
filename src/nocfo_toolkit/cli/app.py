"""Typer application entrypoint for NoCFO CLI."""

from __future__ import annotations

import os
from typing import Literal

import typer

from nocfo_toolkit.cli.commands import (
    accounts,
    auth,
    businesses,
    contacts,
    documents,
    files,
    invoices,
    products,
    purchase_invoices,
    reports,
    tags,
    user,
)
from nocfo_toolkit.cli.context import CommandContext, get_context
from nocfo_toolkit.config import OutputFormat, load_config

app = typer.Typer(help="NoCFO CLI and MCP toolkit", no_args_is_help=True)


@app.callback()
def main_callback(
    ctx: typer.Context,
    api_token: str | None = typer.Option(
        None, help="NoCFO API token (overrides environment and stored config)."
    ),
    base_url: str | None = typer.Option(
        None, help="NoCFO API base URL (defaults to production URL)."
    ),
    output: OutputFormat | None = typer.Option(
        None, "--output", help="Output format for command results."
    ),
    env_file: str | None = typer.Option(
        None, help="Optional path to .env file for local development."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print mutating API requests without sending them.",
    ),
) -> None:
    """Initialize global command context."""

    config = load_config(
        api_token=api_token,
        base_url=base_url,
        output_format=output.value if output else None,
        env_file=env_file,
    )
    ctx.obj = CommandContext(config=config, dry_run=dry_run)


@app.command("mcp")
def run_mcp_server(
    ctx: typer.Context,
    transport: str = typer.Option(
        "stdio",
        "--transport",
        help="MCP transport: stdio for local, http for remote connectors.",
    ),
    host: str = typer.Option(
        "0.0.0.0",  # nosec: B104
        "--host",
        help="Host to bind HTTP transport.",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        min=1,
        max=65535,
        help="Port to bind HTTP transport.",
    ),
    path: str = typer.Option(
        "/mcp",
        "--path",
        help="HTTP path for streamable MCP endpoint.",
    ),
    auth_mode: str = typer.Option(
        "pat",
        "--auth-mode",
        help=(
            "Server auth mode: pat (static token), oauth (remote connector), "
            "or passthrough (forward incoming Authorization header)."
        ),
    ),
    mcp_base_url: str | None = typer.Option(
        None,
        "--mcp-base-url",
        help=(
            "Public base URL for oauth mode (e.g. https://mcp.nocfo.io). "
            "Can also be set via NOCFO_MCP_BASE_URL."
        ),
    ),
    required_scopes: str = typer.Option(
        "",
        "--required-scopes",
        help="Comma-separated OAuth scopes required for MCP tools.",
    ),
    stateless_http: bool = typer.Option(
        False,
        "--stateless-http/--stateful-http",
        help=(
            "Use stateless streamable HTTP mode (recommended behind "
            "load balancers with multiple MCP tasks)."
        ),
    ),
    tool_search: bool = typer.Option(
        True,
        "--tool-search/--no-tool-search",
        help=(
            "Enable FastMCP Tool Search transform to reduce tool-catalog "
            "context by exposing search_tools + call_tool."
        ),
    ),
) -> None:
    """Run NoCFO MCP server over stdio or HTTP transport.

    Stdio mode accepts either NOCFO_JWT_TOKEN or NOCFO_API_TOKEN.
    Optional NOCFO_CLIENT overrides default `nocfo-mcp` x-nocfo-client.
    HTTP oauth mode uses connector bearer verification + JWT exchange flow.
    """

    from nocfo_toolkit.mcp.server import MCPServerOptions, run_http_server, run_server

    command_ctx = get_context(ctx)
    auth_mode_normalized = auth_mode.strip().lower()
    if auth_mode_normalized not in {"pat", "oauth", "passthrough"}:
        raise typer.BadParameter(
            "--auth-mode must be one of 'pat', 'oauth', or 'passthrough'."
        )

    transport_normalized = transport.strip().lower()
    if transport_normalized not in {"stdio", "http"}:
        raise typer.BadParameter("--transport must be either 'stdio' or 'http'.")
    if auth_mode_normalized == "oauth" and transport_normalized != "http":
        raise typer.BadParameter(
            "OAuth mode requires --transport http because remote connectors use HTTP."
        )
    if auth_mode_normalized == "passthrough" and transport_normalized != "http":
        raise typer.BadParameter(
            "Passthrough mode requires --transport http because it forwards "
            "incoming HTTP Authorization headers."
        )

    scope_items = tuple(
        value.strip() for value in required_scopes.split(",") if value.strip()
    )
    auth_mode_value: Literal["pat", "oauth", "passthrough"] = (
        "oauth"
        if auth_mode_normalized == "oauth"
        else ("passthrough" if auth_mode_normalized == "passthrough" else "pat")
    )
    env_tool_search = os.getenv("NOCFO_MCP_TOOL_SEARCH", "").strip().lower()
    tool_search_enabled = (
        env_tool_search in {"1", "true", "yes", "on"}
        if env_tool_search
        else tool_search
    )

    options = MCPServerOptions(
        auth_mode=auth_mode_value,
        mcp_base_url=mcp_base_url or os.getenv("NOCFO_MCP_BASE_URL"),
        required_scopes=scope_items,
        stateless_http=stateless_http,
        tool_search=tool_search_enabled,
    )

    if transport_normalized == "http":
        run_http_server(
            command_ctx.config,
            host=host,
            port=port,
            path=path,
            options=options,
        )
        return

    run_server(command_ctx.config, options=options)


def main() -> None:
    """Console script entrypoint."""

    app()


app.add_typer(auth.app, name="auth")
app.add_typer(businesses.app, name="businesses")
app.add_typer(accounts.app, name="accounts")
app.add_typer(documents.app, name="documents")
app.add_typer(contacts.app, name="contacts")
app.add_typer(invoices.app, name="invoices")
app.add_typer(purchase_invoices.app, name="purchase-invoices")
app.add_typer(products.app, name="products")
app.add_typer(files.app, name="files")
app.add_typer(tags.app, name="tags")
app.add_typer(user.app, name="user")
app.add_typer(reports.app, name="reports")


if __name__ == "__main__":
    main()
