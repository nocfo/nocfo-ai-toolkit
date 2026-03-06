"""Shared CLI context utilities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import typer

from nocfo_toolkit.api_client import ApiClientOptions, NocfoApiClient
from nocfo_toolkit.config import ToolkitConfig


@dataclass(frozen=True)
class CommandContext:
    """Shared context for CLI commands."""

    config: ToolkitConfig
    dry_run: bool = False

    def require_token(self) -> str:
        if not self.config.api_token:
            raise typer.BadParameter(
                "API token is missing. Provide --api-token, set NOCFO_API_TOKEN, "
                "or run `nocfo auth configure`."
            )
        return self.config.api_token

    def api_client(self) -> NocfoApiClient:
        return NocfoApiClient(
            ApiClientOptions(
                base_url=self.config.base_url,
                api_token=self.require_token(),
            )
        )


def get_context(ctx: typer.Context) -> CommandContext:
    """Read and validate typed command context."""

    command_ctx = ctx.obj
    if not isinstance(command_ctx, CommandContext):
        raise RuntimeError("CLI context was not initialized correctly.")
    return command_ctx


def run_async(coro: Any) -> Any:
    """Run coroutine in a command-safe event loop."""

    return asyncio.run(coro)
