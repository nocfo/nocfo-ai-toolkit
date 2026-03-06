"""Account commands."""

from __future__ import annotations

import typer

from nocfo_toolkit.cli.context import get_context, run_async
from nocfo_toolkit.cli.commands._helpers import (
    merge_body,
    parse_key_value_pairs,
    run_list,
    run_request,
)

app = typer.Typer(help="Manage accounts.")


@app.command("list")
def list_accounts(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    query: list[str] = typer.Option(None, "--query", help="Filters as key=value."),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_list(
            command_ctx,
            path=f"/v1/business/{business}/account/",
            params=parse_key_value_pairs(query),
        )
    )


@app.command("get")
def get_account(
    ctx: typer.Context,
    account_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="GET",
            path=f"/v1/business/{business}/account/{account_id}/",
        )
    )


@app.command("create")
def create_account(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    field: list[str] = typer.Option(None, "--field"),
    json_body: str | None = typer.Option(None, "--json-body"),
) -> None:
    command_ctx = get_context(ctx)
    body = merge_body(json_input=json_body, field_pairs=field)
    run_async(
        run_request(
            command_ctx,
            method="POST",
            path=f"/v1/business/{business}/account/",
            body=body,
        )
    )


@app.command("update")
def update_account(
    ctx: typer.Context,
    account_id: int,
    business: str = typer.Option(..., "--business"),
    partial: bool = typer.Option(True, "--partial/--full"),
    field: list[str] = typer.Option(None, "--field"),
    json_body: str | None = typer.Option(None, "--json-body"),
) -> None:
    command_ctx = get_context(ctx)
    body = merge_body(json_input=json_body, field_pairs=field)
    run_async(
        run_request(
            command_ctx,
            method="PATCH" if partial else "PUT",
            path=f"/v1/business/{business}/account/{account_id}/",
            body=body,
        )
    )


@app.command("delete")
def delete_account(
    ctx: typer.Context,
    account_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="DELETE",
            path=f"/v1/business/{business}/account/{account_id}/",
        )
    )
