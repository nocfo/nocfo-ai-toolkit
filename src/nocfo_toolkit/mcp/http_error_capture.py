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
    """Store status/payload for the latest non-success HTTP response."""

    if response.status_code < 400:
        _LAST_HTTP_ERROR.set(None)
        return

    try:
        await response.aread()
    except httpx.HTTPError:
        pass

    try:
        payload: Any = response.json() if response.content else None
    except (ValueError, httpx.ResponseNotRead):
        payload = (response.text or "").strip()[:1000] or None

    _LAST_HTTP_ERROR.set(
        {
            "status_code": response.status_code,
            "payload": payload,
        }
    )
