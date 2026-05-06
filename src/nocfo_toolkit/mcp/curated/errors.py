"""Structured MCP error helpers."""

from __future__ import annotations

import json
from typing import Any

from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.schemas import ToolErrorPayload, dump_model


def raise_tool_error(
    error_type: str,
    message: str,
    hint: str | None = None,
    *,
    status_code: int | None = None,
    field_errors: dict[str, Any] | None = None,
    current_permissions: list[str] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    feature: str | None = None,
    reason: str | None = None,
) -> None:
    payload = ToolErrorPayload(
        error_type=error_type,
        message=message,
        hint=hint,
        status_code=status_code,
        field_errors=field_errors,
        current_permissions=current_permissions,
        candidates=candidates,
        feature=feature,
        reason=reason,
    )
    raise ToolError(json.dumps(dump_model(payload), ensure_ascii=True))


def message_from_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("message", "detail", "error_message", "error_description", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(payload, list):
        return "; ".join(str(item) for item in payload[:3])
    if isinstance(payload, str):
        return payload
    return None


def field_errors(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    ignored = {
        "message",
        "detail",
        "error_message",
        "error_description",
        "error",
        "status_code",
        "error_type",
        "error_code",
        "hint",
    }
    result = {k: v for k, v in payload.items() if k not in ignored}
    return result or None


def error_type(status_code: int) -> str:
    return {
        400: "validation_error",
        401: "authentication_error",
        403: "permission_denied",
        404: "not_found",
        409: "conflict",
        412: "precondition_failed",
        423: "locked",
        429: "rate_limited",
    }.get(status_code, "server_error" if status_code >= 500 else "api_error")


def hint_for_status(status_code: int) -> str | None:
    return {
        400: "Check tool arguments and field errors before retrying.",
        401: "Reconnect authentication and retry.",
        403: "The current user is authenticated but lacks permission for this business/action.",
        404: "Use a list tool with user-facing identifiers to find the correct record.",
        412: "The operation violates a precondition; inspect dependent records first.",
        423: "The resource is locked; unlock or choose an editable record before mutating.",
        429: "Wait briefly before retrying.",
    }.get(status_code)
