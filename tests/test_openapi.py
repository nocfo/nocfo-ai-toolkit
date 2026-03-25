from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from nocfo_toolkit.openapi import filter_mcp_spec, load_openapi_spec


def test_load_openapi_spec_retries_and_succeeds(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}
    cache_path = tmp_path / "openapi.json"
    expected = {"openapi": "3.0.0", "paths": {"/v1/ping/": {"get": {}}}}

    def fake_get(url: str, timeout: float):
        request = httpx.Request("GET", url)
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.HTTPStatusError(
                "server error",
                request=request,
                response=httpx.Response(503, request=request),
            )
        return httpx.Response(200, json=expected, request=request)

    monkeypatch.setattr("nocfo_toolkit.openapi.httpx.get", fake_get)

    result = load_openapi_spec(
        base_url="https://api.example.com",
        cache_path=cache_path,
        max_attempts=3,
        retry_delay_seconds=0,
    )

    assert result == expected
    assert calls["count"] == 3
    assert json.loads(cache_path.read_text(encoding="utf-8")) == expected


def test_load_openapi_spec_falls_back_to_cache(monkeypatch, tmp_path: Path) -> None:
    cache_path = tmp_path / "openapi.json"
    cached = {"openapi": "3.0.0", "paths": {"/v1/cached/": {"get": {}}}}
    cache_path.write_text(json.dumps(cached), encoding="utf-8")

    def always_fails(url: str, timeout: float):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr("nocfo_toolkit.openapi.httpx.get", always_fails)

    result = load_openapi_spec(
        base_url="https://api.example.com",
        cache_path=cache_path,
        max_attempts=2,
        retry_delay_seconds=0,
    )

    assert result == cached


def test_load_openapi_spec_raises_when_network_and_cache_fail(
    monkeypatch, tmp_path: Path
) -> None:
    cache_path = tmp_path / "openapi.json"

    def always_fails(url: str, timeout: float):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr("nocfo_toolkit.openapi.httpx.get", always_fails)

    with pytest.raises(
        RuntimeError,
        match="Failed to load OpenAPI spec from network after retries and no local cache exists.",
    ):
        load_openapi_spec(
            base_url="https://api.example.com",
            cache_path=cache_path,
            max_attempts=2,
            retry_delay_seconds=0,
        )


def test_filter_mcp_spec_excludes_operations_marked_hidden_for_mcp() -> None:
    spec = {
        "paths": {
            "/v1/business/{slug}/account/{id}/": {
                "put": {
                    "operationId": "replace_account",
                    "tags": ["Accounts", "MCP"],
                    "x-mcp-exclude": True,
                },
                "patch": {
                    "operationId": "update_account",
                    "tags": ["Accounts", "MCP"],
                },
            }
        }
    }

    filtered = filter_mcp_spec(spec)
    methods = filtered["paths"]["/v1/business/{slug}/account/{id}/"]

    assert "patch" in methods
    assert "put" not in methods


def test_filter_mcp_spec_keeps_mcp_operation_without_exclude_marker() -> None:
    spec = {
        "paths": {
            "/v1/business/{slug}/header/{id}/": {
                "patch": {
                    "operationId": "update_header",
                    "tags": ["Accounts", "MCP"],
                }
            }
        }
    }

    filtered = filter_mcp_spec(spec)
    methods = filtered["paths"]["/v1/business/{slug}/header/{id}/"]

    assert "patch" in methods
