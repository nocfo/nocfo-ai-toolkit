"""Auth commands."""

from __future__ import annotations

import typer

from nocfo_toolkit.cli.context import CommandContext, get_context
from nocfo_toolkit.cli.output import print_data
from nocfo_toolkit.config import AUTH_HEADER_SCHEME, ConfigStore

app = typer.Typer(help="Configure authentication for NoCFO API.")


@app.command("configure")
def configure_token(
    ctx: typer.Context,
    token: str = typer.Option(..., prompt=True, hide_input=True),
    base_url: str | None = typer.Option(None),
) -> None:
    """Save API token (and optional base URL) to local config."""

    get_context(ctx)  # validates context
    store = ConfigStore()
    store.set_token(token)
    if base_url:
        store.set_base_url(base_url)
    typer.echo("Authentication settings saved.")


@app.command("status")
def auth_status(ctx: typer.Context) -> None:
    """Print current auth and endpoint settings."""

    command_ctx: CommandContext = get_context(ctx)
    print_data(
        {
            "authenticated": command_ctx.config.is_authenticated,
            "token_source": command_ctx.config.token_source.value,
            "auth_header_scheme": AUTH_HEADER_SCHEME,
            "base_url": command_ctx.config.base_url,
            "output_format": command_ctx.config.output_format.value,
        },
        command_ctx.config.output_format,
    )


@app.command("logout")
def logout(ctx: typer.Context) -> None:
    """Clear locally stored API token."""

    get_context(ctx)
    store = ConfigStore()
    store.clear_token()
    typer.echo("Stored API token removed.")
