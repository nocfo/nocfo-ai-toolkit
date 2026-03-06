"""Current user commands."""

from __future__ import annotations

import typer

from nocfo_toolkit.cli.context import get_context, run_async
from nocfo_toolkit.cli.commands._helpers import run_request

app = typer.Typer(help="Inspect current user.")


@app.command("me")
def current_user(ctx: typer.Context) -> None:
    command_ctx = get_context(ctx)
    run_async(run_request(command_ctx, method="GET", path="/v1/user/"))
