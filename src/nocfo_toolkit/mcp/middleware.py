"""MCP middleware for tool logging and error normalization."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams

from nocfo_toolkit.mcp.error_handling import normalize_http_error
from nocfo_toolkit.mcp.http_error_capture import (
    clear_last_http_error,
    get_last_http_error,
)

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "api_key",
}


def _sanitize_for_logs(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return "<truncated>"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in _SENSITIVE_KEYS:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = _sanitize_for_logs(item, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_logs(item, depth=depth + 1) for item in value[:30]]
    return value


class MCPToolErrorMiddleware(Middleware):
    """Logs MCP tool calls and normalizes backend-facing tool errors."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next,
    ):
        tool_name = context.message.name
        arguments = _sanitize_for_logs(context.message.arguments or {})
        started = time.monotonic()
        logger.info(
            "MCP tool call started tool=%s args=%s",
            tool_name,
            json.dumps(arguments, ensure_ascii=True, default=str),
        )

        try:
            result = await call_next(context)
        except ToolError as exc:
            captured = get_last_http_error()
            if not captured:
                raise
            normalized = normalize_http_error(
                tool_name=tool_name,
                status_code=captured.get("status_code"),
                payload=captured.get("payload"),
                fallback_message=str(exc),
            )
            logger.warning(
                "MCP tool call failed tool=%s status=%s error_type=%s summary=%s",
                tool_name,
                normalized.get("status_code"),
                normalized.get("error_type"),
                normalized.get("summary"),
            )
            raise ToolError(json.dumps(normalized, ensure_ascii=True)) from exc
        except Exception:
            logger.exception("MCP tool call crashed tool=%s", tool_name)
            raise
        finally:
            clear_last_http_error()

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "MCP tool call succeeded tool=%s duration_ms=%d",
            tool_name,
            duration_ms,
        )
        return result
