"""Shared helper utilities for command groups."""

from __future__ import annotations

import json
import re
from typing import Any

import typer

from nocfo_toolkit.api_client import NocfoApiError
from nocfo_toolkit.cli.context import CommandContext
from nocfo_toolkit.cli.output import print_data, print_error

_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_SAFE_QUERY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_MAX_JSON_BODY_CHARS = 200_000
_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}


def parse_key_value_pairs(pairs: list[str] | None) -> dict[str, Any]:
    """Parse key=value CLI pairs into dict."""

    parsed: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise typer.BadParameter(f"Expected key=value pair, got '{pair}'.")
        key, raw = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter("Query key cannot be empty.")
        if not _SAFE_QUERY_KEY_PATTERN.match(key):
            raise typer.BadParameter(
                f"Invalid query key '{key}'. Allowed characters: letters, numbers, _, ., :, -"
            )
        value = _coerce_value(raw)
        _assert_safe_string(value, context=f"query value '{key}'")
        parsed[key] = value
    return parsed


def merge_body(
    *,
    json_input: str | None,
    field_pairs: list[str] | None,
) -> dict[str, Any]:
    """Merge body data from JSON string and key=value fields."""

    body: dict[str, Any] = {}
    if json_input:
        if len(json_input) > _MAX_JSON_BODY_CHARS:
            raise typer.BadParameter(
                f"--json-body is too large (max {_MAX_JSON_BODY_CHARS} characters)."
            )
        _assert_safe_string(json_input, context="--json-body")
        try:
            loaded = json.loads(json_input)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter("--json-body must be valid JSON.") from exc
        if not isinstance(loaded, dict):
            raise typer.BadParameter("--json-body must decode to an object.")
        body.update(loaded)
    body.update(parse_key_value_pairs(field_pairs))
    _assert_safe_payload(body, context="request body")
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

    normalized_method = method.upper()
    if command_ctx.dry_run and normalized_method not in _READ_ONLY_METHODS:
        print_data(
            {
                "dry_run": True,
                "method": normalized_method,
                "path": path,
                "params": params or {},
                "body": body or {},
            },
            command_ctx.config.output_format,
        )
        return

    client = command_ctx.api_client()
    try:
        result = await client.request(
            normalized_method,
            path,
            params=params,
            json_body=body,
        )
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


def _assert_safe_payload(value: Any, *, context: str) -> None:
    if isinstance(value, str):
        _assert_safe_string(value, context=context)
        return
    if isinstance(value, dict):
        for nested_key, nested_value in value.items():
            _assert_safe_string(str(nested_key), context=f"{context} key")
            _assert_safe_payload(nested_value, context=f"{context}.{nested_key}")
        return
    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            _assert_safe_payload(nested_value, context=f"{context}[{index}]")


def _assert_safe_string(value: Any, *, context: str) -> None:
    if not isinstance(value, str):
        return
    if _CONTROL_CHARS_PATTERN.search(value):
        raise typer.BadParameter(f"Control characters are not allowed in {context}.")
