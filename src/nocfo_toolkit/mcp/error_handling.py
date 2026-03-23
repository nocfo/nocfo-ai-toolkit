"""Helpers for normalizing backend HTTP errors for MCP clients."""

from __future__ import annotations

from typing import Any

_KNOWN_MESSAGE_KEYS = {
    "detail",
    "message",
    "error",
    "error_description",
    "error_code",
    "error_message",
    "non_field_errors",
}

_STATUS_DEFAULT_SUMMARY: dict[int, str] = {
    400: "Request validation failed.",
    401: "Authentication failed.",
    403: "Permission denied.",
    404: "Resource not found.",
    409: "Request conflicts with current resource state.",
    412: "Request precondition failed.",
    423: "Requested resource is locked.",
    426: "Upgrade required for this operation.",
    429: "Too many requests.",
}

_STATUS_HINTS: dict[int, str] = {
    400: "Review the tool arguments and required fields.",
    401: "Reconnect the MCP integration and retry the tool call.",
    403: "Confirm your account has required permissions for this action.",
    404: "Verify identifiers (business, invoice, contact) are correct.",
    409: "Refresh data and retry once the conflicting state is resolved.",
    412: "Resolve dependent records before retrying this operation.",
    423: "Unlock the resource or close the related locking period before retrying.",
    426: "Operation requires an upgraded plan or additional quota.",
    429: "Wait briefly and retry the request.",
}


def normalize_http_error(
    *,
    tool_name: str,
    status_code: int | None,
    payload: Any | None,
    fallback_message: str,
) -> dict[str, Any]:
    """Build a stable user-facing MCP error payload from structured HTTP context."""

    summary = _extract_summary_from_payload(payload, status_code) or fallback_message
    result: dict[str, Any] = {
        "tool": tool_name,
        "error_type": _error_type_from_status(status_code),
        "summary": summary,
    }

    if status_code is not None:
        result["status_code"] = status_code

    if isinstance(payload, dict):
        error_code = payload.get("error_code")
        if isinstance(error_code, str) and error_code.strip():
            result["backend_error_code"] = error_code

    field_errors = _extract_field_errors(payload)
    if field_errors:
        result["field_errors"] = field_errors

    if status_code in _STATUS_HINTS:
        result["hint"] = _STATUS_HINTS[status_code]

    return result


def _extract_summary_from_payload(payload: Any, status_code: int | None) -> str | None:
    if isinstance(payload, dict):
        for key in ("detail", "message", "error_message", "error_description"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        error_value = payload.get("error")
        if isinstance(error_value, str) and error_value.strip():
            return error_value
    elif isinstance(payload, list):
        parts = [
            item.strip() for item in payload if isinstance(item, str) and item.strip()
        ]
        if parts:
            return "; ".join(parts[:3])
    elif isinstance(payload, str) and payload.strip():
        return payload

    if status_code is not None:
        return _STATUS_DEFAULT_SUMMARY.get(status_code)
    return None


def _extract_field_errors(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    field_errors = {
        key: value
        for key, value in payload.items()
        if key not in _KNOWN_MESSAGE_KEYS
        and (isinstance(value, (list, dict, str, int, float, bool)) or value is None)
    }
    return field_errors or None


def _error_type_from_status(status_code: int | None) -> str:
    if status_code is None:
        return "tool_error"
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "authentication_error"
    if status_code == 403:
        return "permission_error"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 412:
        return "precondition_failed"
    if status_code == 423:
        return "locked"
    if status_code == 426:
        return "upgrade_required"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "server_error"
    return "tool_error"
