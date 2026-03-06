"""Typer application entrypoint for NoCFO CLI."""

from __future__ import annotations

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
) -> None:
    """Initialize global command context."""

    config = load_config(
        api_token=api_token,
        base_url=base_url,
        output_format=output.value if output else None,
        env_file=env_file,
    )
    ctx.obj = CommandContext(config=config)


@app.command("mcp")
def run_mcp_server(ctx: typer.Context) -> None:
    """Run NoCFO MCP server over stdio."""

    from nocfo_toolkit.mcp.server import run_server

    command_ctx = get_context(ctx)
    run_server(command_ctx.config)


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


if __name__ == "__main__":
    main()
