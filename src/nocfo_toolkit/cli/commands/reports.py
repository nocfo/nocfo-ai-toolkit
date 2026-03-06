"""Report commands."""

from __future__ import annotations

from typing import Any

import typer

from nocfo_toolkit.cli.commands._helpers import run_request
from nocfo_toolkit.cli.context import get_context, run_async

app = typer.Typer(help="Generate accounting reports.")


def _run_json_report(
    ctx: typer.Context,
    *,
    business: str,
    report_type: str,
    columns: list[dict[str, Any]],
    extend_accounts: bool,
    append_comparison_columns: bool,
    tag_ids: list[int] | None,
) -> None:
    command_ctx = get_context(ctx)
    body: dict[str, Any] = {
        "type": report_type,
        "columns": columns,
        "extend_accounts": extend_accounts,
        "append_comparison_columns": append_comparison_columns,
    }
    if tag_ids:
        body["tag_ids"] = tag_ids

    run_async(
        run_request(
            command_ctx,
            method="POST",
            path=f"/v1/business/{business}/report/json/",
            body=body,
        )
    )


@app.command("balance-sheet")
def balance_sheet(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    date_at: str = typer.Option(..., "--date-at"),
    extend_accounts: bool = typer.Option(
        True, "--extend-accounts/--no-extend-accounts"
    ),
    append_comparison_columns: bool = typer.Option(
        True, "--append-comparison-columns/--no-append-comparison-columns"
    ),
    tag_id: list[int] = typer.Option(None, "--tag-id"),
) -> None:
    _run_json_report(
        ctx=ctx,
        business=business,
        report_type="BALANCE_SHEET",
        columns=[{"date_at": date_at}],
        extend_accounts=extend_accounts,
        append_comparison_columns=append_comparison_columns,
        tag_ids=tag_id or None,
    )


@app.command("income-statement")
def income_statement(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    date_from: str = typer.Option(..., "--date-from"),
    date_to: str = typer.Option(..., "--date-to"),
    extend_accounts: bool = typer.Option(
        True, "--extend-accounts/--no-extend-accounts"
    ),
    append_comparison_columns: bool = typer.Option(
        True, "--append-comparison-columns/--no-append-comparison-columns"
    ),
    tag_id: list[int] = typer.Option(None, "--tag-id"),
) -> None:
    _run_json_report(
        ctx=ctx,
        business=business,
        report_type="INCOME_STATEMENT",
        columns=[{"date_from": date_from, "date_to": date_to}],
        extend_accounts=extend_accounts,
        append_comparison_columns=append_comparison_columns,
        tag_ids=tag_id or None,
    )


@app.command("ledger")
def ledger(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    date_from: str = typer.Option(..., "--date-from"),
    date_to: str = typer.Option(..., "--date-to"),
    tag_id: list[int] = typer.Option(None, "--tag-id"),
) -> None:
    _run_json_report(
        ctx=ctx,
        business=business,
        report_type="LEDGER",
        columns=[{"date_from": date_from, "date_to": date_to}],
        extend_accounts=False,
        append_comparison_columns=False,
        tag_ids=tag_id or None,
    )


@app.command("journal")
def journal(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    date_from: str = typer.Option(..., "--date-from"),
    date_to: str = typer.Option(..., "--date-to"),
    tag_id: list[int] = typer.Option(None, "--tag-id"),
) -> None:
    _run_json_report(
        ctx=ctx,
        business=business,
        report_type="JOURNAL",
        columns=[{"date_from": date_from, "date_to": date_to}],
        extend_accounts=False,
        append_comparison_columns=False,
        tag_ids=tag_id or None,
    )


@app.command("vat")
def vat(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    date_from: str = typer.Option(..., "--date-from"),
    date_to: str = typer.Option(..., "--date-to"),
    tag_id: list[int] = typer.Option(None, "--tag-id"),
) -> None:
    _run_json_report(
        ctx=ctx,
        business=business,
        report_type="VAT_REPORT",
        columns=[{"date_from": date_from, "date_to": date_to}],
        extend_accounts=False,
        append_comparison_columns=False,
        tag_ids=tag_id or None,
    )
