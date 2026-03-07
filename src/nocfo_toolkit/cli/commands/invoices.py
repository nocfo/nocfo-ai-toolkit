"""Sales invoice commands."""

from __future__ import annotations

import typer

from nocfo_toolkit.cli.context import get_context, run_async
from nocfo_toolkit.cli.commands._helpers import (
    merge_body,
    parse_key_value_pairs,
    run_list,
    run_request,
)

app = typer.Typer(help="Manage sales invoices.")

_LIST_COLUMNS = ("id", "invoice_number", "friendly_name", "total_amount", "status")


@app.command("list")
def list_invoices(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    query: list[str] = typer.Option(None, "--query"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results per page."),
    all_pages: bool = typer.Option(False, "--all", help="Fetch all pages."),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_list(
            command_ctx,
            path=f"/v1/invoicing/{business}/invoice/",
            params=parse_key_value_pairs(query),
            columns=_LIST_COLUMNS,
            page_size=limit,
            fetch_all=all_pages,
        )
    )


@app.command("get")
def get_invoice(
    ctx: typer.Context,
    invoice_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="GET",
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/",
        )
    )


@app.command("create")
def create_invoice(
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
            path=f"/v1/invoicing/{business}/invoice/",
            body=body,
        )
    )


@app.command("update")
def update_invoice(
    ctx: typer.Context,
    invoice_id: int,
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
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/",
            body=body,
        )
    )


@app.command("delete")
def delete_invoice(
    ctx: typer.Context,
    invoice_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="DELETE",
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/",
        )
    )


@app.command("accept")
def accept_invoice(
    ctx: typer.Context,
    invoice_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="POST",
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/actions/accept/",
        )
    )


@app.command("send")
def send_invoice(
    ctx: typer.Context,
    invoice_id: int,
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
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/send/",
            body=body or None,
        )
    )


@app.command("paid")
def set_paid(
    ctx: typer.Context,
    invoice_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="POST",
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/actions/paid/",
        )
    )


@app.command("unpaid")
def set_unpaid(
    ctx: typer.Context,
    invoice_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="POST",
            path=f"/v1/invoicing/{business}/invoice/{invoice_id}/actions/unpaid/",
        )
    )
