"""Report commands."""

from __future__ import annotations

import json
from typing import Any

import typer

from nocfo_toolkit.api_client import NocfoApiError
from nocfo_toolkit.cli.context import get_context, run_async
from nocfo_toolkit.cli.output import print_data, print_error

app = typer.Typer(help="Generate accounting reports.")


def _run_json_report(
    ctx: typer.Context,
    *,
    business: str,
    path: str,
    columns: list[dict[str, Any]],
    extend_accounts: bool,
    append_comparison_columns: bool,
    tag_ids: list[int] | None,
) -> None:
    command_ctx = get_context(ctx)
    body: dict[str, Any] = {
        "columns": columns,
        "extend_accounts": extend_accounts,
        "append_comparison_columns": append_comparison_columns,
    }
    if tag_ids:
        body["tag_ids"] = tag_ids

    run_async(
        _run_report_request(
            command_ctx=command_ctx,
            path=f"/v1/business/{business}/report/{path}/",
            body=body,
        )
    )


async def _run_report_request(
    *,
    command_ctx,
    path: str,
    body: dict[str, Any],
) -> None:
    client = command_ctx.api_client()
    try:
        result = await client.request("POST", path, json_body=body)

        # Some report endpoints can return JSON encoded as a string.
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, (dict, list)):
                    result = parsed
            except json.JSONDecodeError:
                pass

        if isinstance(result, dict):
            result.pop("report_type", None)

        if result is not None:
            print_data(result, command_ctx.config.output_format)
    except NocfoApiError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        await client.close()


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
        path="balance-sheet",
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
        path="income-statement",
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
        path="ledger",
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
        path="journal",
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
        path="vat-report",
        columns=[{"date_from": date_from, "date_to": date_to}],
        extend_accounts=False,
        append_comparison_columns=False,
        tag_ids=tag_id or None,
    )


@app.command("balance-sheet-short")
def balance_sheet_short(
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
        path="balance-sheet-short",
        columns=[{"date_at": date_at}],
        extend_accounts=extend_accounts,
        append_comparison_columns=append_comparison_columns,
        tag_ids=tag_id or None,
    )


@app.command("income-statement-short")
def income_statement_short(
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
        path="income-statement-short",
        columns=[{"date_from": date_from, "date_to": date_to}],
        extend_accounts=extend_accounts,
        append_comparison_columns=append_comparison_columns,
        tag_ids=tag_id or None,
    )


@app.command("equity-changes")
def equity_changes(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    date_at: str = typer.Option(..., "--date-at"),
    extend_accounts: bool = typer.Option(
        False, "--extend-accounts/--no-extend-accounts"
    ),
    append_comparison_columns: bool = typer.Option(
        False, "--append-comparison-columns/--no-append-comparison-columns"
    ),
    tag_id: list[int] = typer.Option(None, "--tag-id"),
) -> None:
    _run_json_report(
        ctx=ctx,
        business=business,
        path="equity-changes",
        columns=[{"date_at": date_at}],
        extend_accounts=extend_accounts,
        append_comparison_columns=append_comparison_columns,
        tag_ids=tag_id or None,
    )
