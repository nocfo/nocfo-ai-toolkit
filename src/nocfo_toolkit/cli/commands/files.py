"""File commands."""

from __future__ import annotations

from pathlib import Path

import typer

from nocfo_toolkit.api_client import NocfoApiError
from nocfo_toolkit.cli.context import get_context, run_async
from nocfo_toolkit.cli.commands._helpers import (
    parse_key_value_pairs,
    run_list,
    run_request,
)
from nocfo_toolkit.cli.output import print_data, print_error

app = typer.Typer(help="Manage files and uploads.")


@app.command("list")
def list_files(
    ctx: typer.Context,
    business: str = typer.Option(..., "--business"),
    query: list[str] = typer.Option(None, "--query"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_list(
            command_ctx,
            path=f"/v1/business/{business}/files/",
            params=parse_key_value_pairs(query),
        )
    )


@app.command("get")
def get_file(
    ctx: typer.Context,
    file_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="GET",
            path=f"/v1/business/{business}/files/{file_id}/",
        )
    )


@app.command("upload")
def upload_file(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True),
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(_upload_file(command_ctx, business_slug=business, file_path=path))


async def _upload_file(command_ctx, *, business_slug: str, file_path: Path) -> None:
    client = command_ctx.api_client()
    try:
        with file_path.open("rb") as file_obj:
            response = await client._client.post(  # noqa: SLF001
                f"/v1/business/{business_slug}/file_upload/",
                files={"file": (file_path.name, file_obj)},
            )
        result = client._decode_or_raise(response)  # noqa: SLF001
        print_data(result, command_ctx.config.output_format)
    except (OSError, NocfoApiError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        await client.close()


@app.command("delete")
def delete_file(
    ctx: typer.Context,
    file_id: int,
    business: str = typer.Option(..., "--business"),
) -> None:
    command_ctx = get_context(ctx)
    run_async(
        run_request(
            command_ctx,
            method="DELETE",
            path=f"/v1/business/{business}/files/{file_id}/",
        )
    )
