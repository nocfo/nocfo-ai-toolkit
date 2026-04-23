"""Context-local capture of recent downstream HTTP errors."""

from __future__ import annotations

import contextvars
from typing import Any

import httpx

_LAST_HTTP_ERROR: contextvars.ContextVar[
    dict[str, Any] | None
] = contextvars.ContextVar("nocfo_last_http_error", default=None)


def clear_last_http_error() -> None:
    _LAST_HTTP_ERROR.set(None)


def get_last_http_error() -> dict[str, Any] | None:
    return _LAST_HTTP_ERROR.get()


async def capture_http_error_response(response: httpx.Response) -> None:
    """Store status/payload for the latest HTTP response.

    FastMCP can issue downstream requests with streaming enabled. In that mode,
    accessing ``response.content``/``response.json`` without ``aread()`` raises
    ``ResponseNotRead``. We therefore always drain the body first, even for
    success responses, so tool handlers can safely decode the payload.
    """

    try:
        await response.aread()
    except (httpx.HTTPError, httpx.StreamError):
        # Keep best-effort behavior: failures here should not shadow the original
        # tool error path. The middleware still clears stale captured state below.
        _LAST_HTTP_ERROR.set(None)
        return

    if response.status_code < 400:
        _LAST_HTTP_ERROR.set(None)
        return

    try:
        payload: Any = response.json() if response.content else None
    except ValueError:
        text = response.text.strip()
        payload = text[:1000] if text else None

    _LAST_HTTP_ERROR.set(
        {
            "status_code": response.status_code,
            "payload": payload,
        }
    )
