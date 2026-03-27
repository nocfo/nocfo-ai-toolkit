"""Typer application entrypoint for NoCFO CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

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
    schema,
    tags,
    user,
)
from nocfo_toolkit.cli.context import CommandContext, get_context
from nocfo_toolkit.config import OutputFormat, load_config
from nocfo_toolkit.mcp.server import MCPServerOptions

app = typer.Typer(help="NoCFO CLI and MCP toolkit", no_args_is_help=True)


def _is_local_base_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"}


# watchfiles.run_process spawns a child and must pickle ``target``; keep this at module level.
_ENV_WATCH_HOST = "NOCFO_MCP_WATCH_HOST"
_ENV_WATCH_PORT = "NOCFO_MCP_WATCH_PORT"
_ENV_WATCH_PATH = "NOCFO_MCP_WATCH_PATH"
_ENV_WATCH_AUTH_MODE = "NOCFO_MCP_WATCH_AUTH_MODE"
_ENV_WATCH_MCP_BASE_URL = "NOCFO_MCP_WATCH_MCP_BASE_URL"
_ENV_WATCH_REQUIRED_SCOPES = "NOCFO_MCP_WATCH_REQUIRED_SCOPES"


def _apply_watch_child_env_from_context(
    command_ctx: CommandContext,
    *,
    host: str,
    port: int,
    path: str,
    options: MCPServerOptions,
) -> None:
    """Expose parent CLI-resolved config to the watch child via ``os.environ``."""
    os.environ["NOCFO_BASE_URL"] = command_ctx.config.base_url
    if command_ctx.config.api_token:
        os.environ["NOCFO_API_TOKEN"] = command_ctx.config.api_token
    else:
        os.environ.pop("NOCFO_API_TOKEN", None)
    if command_ctx.config.jwt_token:
        os.environ["NOCFO_JWT_TOKEN"] = command_ctx.config.jwt_token
    else:
        os.environ.pop("NOCFO_JWT_TOKEN", None)
    os.environ[_ENV_WATCH_HOST] = host
    os.environ[_ENV_WATCH_PORT] = str(port)
    os.environ[_ENV_WATCH_PATH] = path
    os.environ[_ENV_WATCH_AUTH_MODE] = options.auth_mode
    if options.mcp_base_url:
        os.environ[_ENV_WATCH_MCP_BASE_URL] = options.mcp_base_url
    else:
        os.environ.pop(_ENV_WATCH_MCP_BASE_URL, None)
    os.environ[_ENV_WATCH_REQUIRED_SCOPES] = ",".join(options.required_scopes)


def mcp_watch_http_worker() -> None:
    """Subprocess entry for ``watchfiles.run_process`` (must be picklable / top-level)."""
    from nocfo_toolkit.config import load_config
    from nocfo_toolkit.mcp.server import MCPServerOptions, run_http_server

    host = os.environ[_ENV_WATCH_HOST]
    port = int(os.environ[_ENV_WATCH_PORT])
    path = os.environ[_ENV_WATCH_PATH]
    auth_mode_raw = os.environ[_ENV_WATCH_AUTH_MODE].strip().lower()
    if auth_mode_raw not in {"pat", "oauth"}:
        raise RuntimeError(
            f"Invalid {_ENV_WATCH_AUTH_MODE}: {auth_mode_raw!r} (expected pat|oauth)"
        )
    auth_mode: Literal["pat", "oauth"] = auth_mode_raw  # type: ignore[assignment]
    scopes_raw = os.environ.get(_ENV_WATCH_REQUIRED_SCOPES, "")
    scopes = tuple(s.strip() for s in scopes_raw.split(",") if s.strip())
    mcp_base = os.environ.get(_ENV_WATCH_MCP_BASE_URL)
    config = load_config()
    options = MCPServerOptions(
        auth_mode=auth_mode,
        mcp_base_url=mcp_base,
        required_scopes=scopes,
    )
    run_http_server(
        config,
        host=host,
        port=port,
        path=path,
        options=options,
    )


def _run_mcp_with_watch(
    *,
    command_ctx: CommandContext,
    transport: Literal["stdio", "http"],
    host: str,
    port: int,
    path: str,
    options: MCPServerOptions,
    watch_paths: list[str] | None,
) -> None:
    try:
        from watchfiles import PythonFilter, run_process
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency should exist
        raise RuntimeError(
            "Watch mode requires `watchfiles`. Install dependencies and retry."
        ) from exc

    if transport != "http":
        raise typer.BadParameter("--watch currently supports --transport http only.")
    if not _is_local_base_url(command_ctx.config.base_url):
        raise typer.BadParameter(
            "--watch is allowed only with local backend base URL "
            "(localhost/127.0.0.1/::1)."
        )

    resolved_watch_paths = watch_paths or ["src", "pyproject.toml"]
    missing_paths = [
        path_item for path_item in resolved_watch_paths if not Path(path_item).exists()
    ]
    if missing_paths:
        missing_str = ", ".join(missing_paths)
        raise typer.BadParameter(f"--watch-path does not exist: {missing_str}")

    _apply_watch_child_env_from_context(
        command_ctx,
        host=host,
        port=port,
        path=path,
        options=options,
    )

    typer.echo(
        "Starting MCP in watch mode (local dev). "
        f"Watching: {', '.join(resolved_watch_paths)}"
    )
    run_process(
        *resolved_watch_paths,
        target=mcp_watch_http_worker,
        watch_filter=PythonFilter(extra_extensions=(".toml", ".yaml", ".yml", ".json")),
    )


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
        help="Server auth mode: pat (legacy) or oauth (Claude/OpenAI remote).",
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
    watch: bool = typer.Option(
        False,
        "--watch/--no-watch",
        help="Auto-restart MCP server on local file changes (local dev only).",
    ),
    watch_paths: list[str] | None = typer.Option(
        None,
        "--watch-path",
        help="Additional watch path. Can be repeated.",
    ),
) -> None:
    """Run NoCFO MCP server over stdio or HTTP transport.

    Stdio mode accepts either NOCFO_JWT_TOKEN or NOCFO_API_TOKEN.
    HTTP oauth mode uses connector bearer verification + JWT exchange flow.
    """

    from nocfo_toolkit.mcp.server import run_http_server, run_server

    command_ctx = get_context(ctx)
    auth_mode_normalized = auth_mode.strip().lower()
    if auth_mode_normalized not in {"pat", "oauth"}:
        raise typer.BadParameter("--auth-mode must be either 'pat' or 'oauth'.")

    transport_normalized = transport.strip().lower()
    if transport_normalized not in {"stdio", "http"}:
        raise typer.BadParameter("--transport must be either 'stdio' or 'http'.")
    if auth_mode_normalized == "oauth" and transport_normalized != "http":
        raise typer.BadParameter(
            "OAuth mode requires --transport http because remote connectors use HTTP."
        )

    scope_items = tuple(
        value.strip() for value in required_scopes.split(",") if value.strip()
    )
    auth_mode_value: Literal["pat", "oauth"] = (
        "oauth" if auth_mode_normalized == "oauth" else "pat"
    )
    options = MCPServerOptions(
        auth_mode=auth_mode_value,
        mcp_base_url=mcp_base_url or os.getenv("NOCFO_MCP_BASE_URL"),
        required_scopes=scope_items,
    )

    if watch:
        _run_mcp_with_watch(
            command_ctx=command_ctx,
            transport=transport_normalized,  # type: ignore[arg-type]
            host=host,
            port=port,
            path=path,
            options=options,
            watch_paths=watch_paths,
        )
        return

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
app.add_typer(schema.app, name="schema")


if __name__ == "__main__":
    main()
