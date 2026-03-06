"""Shared helper utilities for command groups."""

from __future__ import annotations

import json
from typing import Any

import typer

from nocfo_toolkit.api_client import NocfoApiError
from nocfo_toolkit.cli.context import CommandContext
from nocfo_toolkit.cli.output import print_data, print_error


def parse_key_value_pairs(pairs: list[str] | None) -> dict[str, Any]:
    """Parse key=value CLI pairs into dict."""

    parsed: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise typer.BadParameter(f"Expected key=value pair, got '{pair}'.")
        key, raw = pair.split("=", 1)
        parsed[key] = _coerce_value(raw)
    return parsed


def merge_body(
    *,
    json_input: str | None,
    field_pairs: list[str] | None,
) -> dict[str, Any]:
    """Merge body data from JSON string and key=value fields."""

    body: dict[str, Any] = {}
    if json_input:
        try:
            loaded = json.loads(json_input)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter("--json-body must be valid JSON.") from exc
        if not isinstance(loaded, dict):
            raise typer.BadParameter("--json-body must decode to an object.")
        body.update(loaded)
    body.update(parse_key_value_pairs(field_pairs))
    return body


async def run_list(
    command_ctx: CommandContext,
    *,
    path: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Execute list command and print output."""

    client = command_ctx.api_client()
    try:
        results = await client.list_paginated(path, params=params)
        print_data(results, command_ctx.config.output_format)
    except NocfoApiError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        await client.close()


async def run_request(
    command_ctx: CommandContext,
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> None:
    """Execute request command and print output."""

    client = command_ctx.api_client()
    try:
        result = await client.request(method, path, params=params, json_body=body)
        if result is not None:
            print_data(result, command_ctx.config.output_format)
    except NocfoApiError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        await client.close()


def _coerce_value(value: str) -> Any:
    raw = value.strip()
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    if raw.lower() == "null":
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw
