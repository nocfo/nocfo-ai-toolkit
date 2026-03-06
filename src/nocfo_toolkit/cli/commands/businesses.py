"""Business commands."""

from __future__ import annotations

import typer

from nocfo_toolkit.cli.context import get_context, run_async
from nocfo_toolkit.cli.commands._helpers import (
    merge_body,
    parse_key_value_pairs,
    run_list,
    run_request,
)

app = typer.Typer(help="Manage businesses.")


@app.command("list")
def list_businesses(
    ctx: typer.Context,
    query: list[str] = typer.Option(None, "--query", help="Filters as key=value."),
) -> None:
    command_ctx = get_context(ctx)
    params = parse_key_value_pairs(query)
    run_async(run_list(command_ctx, path="/v1/business/", params=params))


@app.command("get")
def get_business(ctx: typer.Context, business_slug: str) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(command_ctx, method="GET", path=f"/v1/business/{business_slug}/")
    )


@app.command("create")
def create_business(
    ctx: typer.Context,
    field: list[str] = typer.Option(None, "--field", help="Body field as key=value."),
    json_body: str | None = typer.Option(None, "--json-body"),
) -> None:
    command_ctx = get_context(ctx)
    body = merge_body(json_input=json_body, field_pairs=field)
    run_async(run_request(command_ctx, method="POST", path="/v1/business/", body=body))


@app.command("update")
def update_business(
    ctx: typer.Context,
    business_slug: str,
    partial: bool = typer.Option(True, "--partial/--full"),
    field: list[str] = typer.Option(None, "--field", help="Body field as key=value."),
    json_body: str | None = typer.Option(None, "--json-body"),
) -> None:
    command_ctx = get_context(ctx)
    body = merge_body(json_input=json_body, field_pairs=field)
    method = "PATCH" if partial else "PUT"
    run_async(
        run_request(
            command_ctx,
            method=method,
            path=f"/v1/business/{business_slug}/",
            body=body,
        )
    )


@app.command("delete")
def delete_business(ctx: typer.Context, business_slug: str) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(command_ctx, method="DELETE", path=f"/v1/business/{business_slug}/")
    )
