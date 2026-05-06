"""Shared projection and pagination helpers for curated MCP tools."""

from __future__ import annotations

import base64
import json
from typing import Any

from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import tool_handle


def b64_json(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def encode_tool_handle(resource: str, internal_id: int) -> str:
    return tool_handle(resource, internal_id)


def decode_tool_handle(handle: str, *, expected_resource: str | None = None) -> int:
    try:
        raw = base64.urlsafe_b64decode(handle.encode("ascii")).decode("utf-8")
        parsed = json.loads(raw)
        resource = str(parsed.get("resource") or "")
        internal_id = int(parsed["id"])
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise_tool_error(
            "invalid_reference",
            "tool_handle is invalid.",
            "Use the exact tool_handle returned by a list/retrieve response.",
            status_code=400,
        )
    if expected_resource and resource != expected_resource:
        raise_tool_error(
            "invalid_reference",
            f"tool_handle belongs to {resource or 'another resource'}, not {expected_resource}.",
            f"Use a {expected_resource} tool_handle from the matching list tool.",
            status_code=400,
        )
    if internal_id < 1:
        raise_tool_error(
            "invalid_reference",
            "tool_handle is invalid.",
            "Use the exact tool_handle returned by a list/retrieve response.",
            status_code=400,
        )
    return internal_id


def parse_cursor(cursor: str | None) -> int:
    if not cursor:
        return 1
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        parsed = json.loads(raw)
        page = int(parsed.get("page", 1))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise_tool_error(
            "invalid_cursor",
            "Pagination cursor is invalid.",
            "Use the exact next_cursor value returned by the previous list call.",
            status_code=400,
        )
    return max(page, 1)


def jwt_business_slug(jwt_token: str | None) -> str | None:
    if not jwt_token:
        return None
    token = jwt_token.strip()
    lowered = token.lower()
    for prefix in ("token ", "bearer "):
        if lowered.startswith(prefix):
            token = token[len(prefix) :].strip()
            break
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        padding = "=" * (-len(parts[1]) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
        )
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    # Backend contract: JwtTokenAuthentication reads business scope from
    # `payload["business_slug"]` only.
    value = payload.get("business_slug")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() == "current":
        return None
    return normalized


def items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def project(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    if not fields:
        return dict(item)
    return {field: item.get(field) for field in fields if field in item}


def project_business(item: dict[str, Any]) -> dict[str, Any]:
    return project(item, ("slug", "name", "form_name", "identifiers"))


def report_body(
    report: Any,
    tag_ids: list[int] | None = None,
) -> dict[str, Any]:
    columns = [
        column.model_dump(mode="json", exclude_none=True) for column in report.columns
    ]
    body: dict[str, Any] = {
        "columns": columns,
        "extend_accounts": report.extend_accounts,
        "append_comparison_columns": report.append_comparison_columns,
    }
    if tag_ids:
        body["tag_ids"] = tag_ids
    return body
