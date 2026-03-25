from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams

from nocfo_toolkit.mcp.error_handling import normalize_http_error
from nocfo_toolkit.mcp.http_error_capture import (
    capture_http_error_response,
    clear_last_http_error,
    get_last_http_error,
)
from nocfo_toolkit.mcp.middleware import MCPToolErrorMiddleware


class _UnreadAsyncStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"detail":"streamed failure"}'

    async def aclose(self) -> None:
        return None


class _BrokenAsyncStream(httpx.AsyncByteStream):
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise httpx.ReadError("stream failed")

    async def aclose(self) -> None:
        return None


def test_normalize_http_error_supports_drf_detail_shape() -> None:
    payload = {"detail": "business_slug is required", "business_slug": ["required"]}
    normalized = normalize_http_error(
        tool_name="list_invoices",
        status_code=400,
        payload=payload,
        fallback_message="fallback",
    )

    assert normalized["tool"] == "list_invoices"
    assert normalized["status_code"] == 400
    assert normalized["error_type"] == "bad_request"
    assert normalized["summary"] == "business_slug is required"
    assert normalized["field_errors"] == {"business_slug": ["required"]}
    assert "hint" in normalized


def test_normalize_http_error_supports_oauth_shape() -> None:
    payload = {
        "error": "invalid_client_metadata",
        "error_description": "redirect_uris must be a non-empty array.",
    }
    normalized = normalize_http_error(
        tool_name="register_client",
        status_code=400,
        payload=payload,
        fallback_message="fallback",
    )

    assert normalized["status_code"] == 400
    assert normalized["summary"] == "redirect_uris must be a non-empty array."


def test_normalize_http_error_handles_status_only_conflict() -> None:
    normalized = normalize_http_error(
        tool_name="close_period",
        status_code=423,
        payload=None,
        fallback_message="fallback",
    )

    assert normalized["status_code"] == 423
    assert normalized["error_type"] == "locked"
    assert normalized["summary"] == "Requested resource is locked."


def test_middleware_uses_captured_http_error_context() -> None:
    middleware = MCPToolErrorMiddleware()
    context = MiddlewareContext(
        message=CallToolRequestParams(name="create_invoice", arguments={}),
        source="client",
        type="request",
        method="tools/call",
    )

    async def call_next(_: MiddlewareContext[CallToolRequestParams]):
        request = httpx.Request("POST", "https://api.example.com/v1/invoices/")
        response = httpx.Response(
            400, request=request, json={"detail": "business_slug is required"}
        )
        await capture_http_error_response(response)
        raise ToolError("Error calling tool 'create_invoice': upstream failure")

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(middleware.on_call_tool(context, call_next))

    normalized = json.loads(str(exc_info.value))
    assert normalized["tool"] == "create_invoice"
    assert normalized["status_code"] == 400
    assert normalized["summary"] == "business_slug is required"


def test_middleware_keeps_non_http_tool_error() -> None:
    middleware = MCPToolErrorMiddleware()
    context = MiddlewareContext(
        message=CallToolRequestParams(name="create_invoice", arguments={}),
        source="client",
        type="request",
        method="tools/call",
    )

    async def call_next(_: MiddlewareContext[CallToolRequestParams]):
        raise ToolError("Unexpected validation failure")

    with pytest.raises(ToolError, match="Unexpected validation failure"):
        asyncio.run(middleware.on_call_tool(context, call_next))


def test_capture_http_error_response_reads_unread_streaming_response() -> None:
    request = httpx.Request("GET", "https://api.example.com/v1/businesses/")
    response = httpx.Response(400, request=request, stream=_UnreadAsyncStream())

    asyncio.run(capture_http_error_response(response))

    assert response.json() == {"detail": "streamed failure"}


def test_capture_http_error_response_reads_success_streaming_response() -> None:
    request = httpx.Request("GET", "https://api.example.com/v1/businesses/")
    response = httpx.Response(200, request=request, stream=_UnreadAsyncStream())

    asyncio.run(capture_http_error_response(response))

    assert response.json() == {"detail": "streamed failure"}


def test_capture_http_error_response_handles_broken_stream_without_crashing() -> None:
    clear_last_http_error()
    request = httpx.Request("GET", "https://api.example.com/v1/businesses/")
    response = httpx.Response(400, request=request, stream=_BrokenAsyncStream())

    async def run() -> None:
        await capture_http_error_response(response)
        assert get_last_http_error() is None

    asyncio.run(run())
