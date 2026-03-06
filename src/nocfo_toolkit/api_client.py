"""Shared NoCFO API client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from nocfo_toolkit.config import AUTH_HEADER_SCHEME


class NocfoApiError(RuntimeError):
    """Raised when NoCFO API returns a non-success response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ApiClientOptions:
    """Runtime options for API client."""

    base_url: str
    api_token: str
    timeout_seconds: float = 30.0


class NocfoApiClient:
    """Async API client used by CLI and MCP components."""

    def __init__(self, options: ApiClientOptions) -> None:
        self.options = options
        self._client = httpx.AsyncClient(
            base_url=options.base_url.rstrip("/"),
            timeout=options.timeout_seconds,
            headers={
                "Authorization": f"{AUTH_HEADER_SCHEME} {options.api_token}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        """Perform an API request and return decoded JSON, if any."""

        response = await self._client.request(
            method=method.upper(),
            url=path,
            params={k: v for k, v in (params or {}).items() if v is not None},
            json=json_body,
        )
        return self._decode_or_raise(response)

    async def list_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch paginated list endpoint and return merged results."""

        all_results: list[dict[str, Any]] = []
        current_page = 1

        while current_page <= max_pages:
            query = dict(params or {})
            query.setdefault("page", current_page)
            page_data = await self.request("GET", path, params=query)

            if isinstance(page_data, dict) and "results" in page_data:
                results = page_data.get("results") or []
                if not isinstance(results, list):
                    raise NocfoApiError("Unexpected paginated response format.")
                all_results.extend(results)

                if not page_data.get("next"):
                    break
                current_page += 1
                continue

            # Endpoint is not paginated.
            if isinstance(page_data, list):
                return page_data
            raise NocfoApiError("Expected list or paginated object response.")

        return all_results

    @staticmethod
    def _decode_or_raise(response: httpx.Response) -> Any:
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = (
                    payload.get("detail") if isinstance(payload, dict) else str(payload)
                )
            except ValueError:
                message = response.text or "Unknown API error"
            if response.status_code in {401, 403}:
                message = (
                    "Authentication failed. Verify NOCFO_API_TOKEN (PAT) and ensure "
                    "Authorization header uses 'Token <PAT>'."
                )
            raise NocfoApiError(message, status_code=response.status_code)

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise NocfoApiError("API response was not valid JSON.") from exc


@asynccontextmanager
async def create_api_client(options: ApiClientOptions) -> AsyncIterator[NocfoApiClient]:
    """Context manager for lifecycle-safe API client usage."""

    client = NocfoApiClient(options)
    try:
        yield client
    finally:
        await client.close()
