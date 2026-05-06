"""MCP middleware for tool logging and error normalization."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import CallToolRequestParams
from mcp.types import ListToolsRequest
from mcp.types import Tool as MCPTool

from nocfo_toolkit.mcp.error_handling import normalize_http_error
from nocfo_toolkit.mcp.http_error_capture import (
    clear_last_http_error,
    get_last_http_error,
)
from nocfo_toolkit.mcp.tool_access import (
    ToolAccessProfile,
    current_request_tool_access_profile,
    is_tool_allowed_for_request_profile,
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


class MCPToolAccessMiddleware(Middleware):
    """Filter listed/called tools by the active request access profile."""

    async def on_list_tools(
        self,
        context: MiddlewareContext[ListToolsRequest],
        call_next,
    ) -> Sequence[MCPTool]:
        tools = await call_next(context)
        profile = current_request_tool_access_profile()
        if profile is ToolAccessProfile.ALL:
            return tools
        return [
            tool
            for tool in tools
            if is_tool_allowed_for_request_profile(tags=tool.tags, profile=profile)
        ]

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next,
    ):
        profile = current_request_tool_access_profile()
        if profile is ToolAccessProfile.ALL:
            return await call_next(context)
        tool_name = context.message.name
        fastmcp_context = context.fastmcp_context
        fastmcp = getattr(fastmcp_context, "fastmcp", None)
        tool = await fastmcp.get_tool(tool_name) if fastmcp is not None else None
        if tool is not None and not is_tool_allowed_for_request_profile(
            tags=tool.tags,
            profile=profile,
        ):
            raise ToolError(
                json.dumps(
                    {
                        "error_type": "tool_not_available",
                        "summary": f"Tool '{tool_name}' is not available.",
                        "status_code": 403,
                    },
                    ensure_ascii=True,
                )
            )
        return await call_next(context)
