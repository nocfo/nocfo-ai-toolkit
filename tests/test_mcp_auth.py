from __future__ import annotations

import asyncio
import base64
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from nocfo_toolkit.mcp.auth import JwtExchangeAuth, MCPAuthConfigurationError
from nocfo_toolkit.mcp.server import MCPServerOptions, create_server
from nocfo_toolkit.config import OutputFormat, TokenSource, ToolkitConfig


def _minimal_openapi_spec(base_url: str) -> dict[str, object]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "NoCFO", "version": "1.0.0"},
        "servers": [{"url": base_url}],
        "paths": {
            "/v1/example/": {
                "get": {
                    "operationId": "example",
                    "tags": ["MCP"],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }


def _build_unverified_jwt_with_exp(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode("utf-8")).decode(
        "utf-8"
    )
    payload = payload.rstrip("=")
    return f"header.{payload}.signature"


def test_jwt_exchange_auth_exchanges_once_and_uses_cache(monkeypatch) -> None:
    exchange_calls = {"count": 0}
    expected_jwt = _build_unverified_jwt_with_exp(int(time.time()) + 3600)

    def fake_access_token():
        return SimpleNamespace(
            token="incoming-bearer",
            claims={"sub": "user-1"},
        )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/jwt/":
            exchange_calls["count"] += 1
            assert request.headers["Authorization"] == "Bearer incoming-bearer"
            return httpx.Response(200, json={"token": expected_jwt})

        assert request.headers["Authorization"] == f"Token {expected_jwt}"
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("nocfo_toolkit.mcp.auth.get_access_token", fake_access_token)
    auth = JwtExchangeAuth()

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            base_url="https://api.example.com",
            transport=transport,
            auth=auth,
        ) as client:
            response_a = await client.get("/v1/businesses/")
            response_b = await client.get("/v1/businesses/")
            assert response_a.status_code == 200
            assert response_b.status_code == 200

    asyncio.run(run())
    assert exchange_calls["count"] == 1


def test_jwt_exchange_auth_requires_bearer(monkeypatch) -> None:
    monkeypatch.setattr("nocfo_toolkit.mcp.auth.get_access_token", lambda: None)
    auth = JwtExchangeAuth()

    async def run() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        async with httpx.AsyncClient(
            base_url="https://api.example.com",
            transport=transport,
            auth=auth,
        ) as client:
            await client.get("/v1/businesses/")

    with pytest.raises(RuntimeError, match="Missing OAuth bearer token"):
        asyncio.run(run())


def test_create_server_oauth_mode_requires_public_base_url(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        _minimal_openapi_spec,
    )

    with pytest.raises(MCPAuthConfigurationError, match="Missing MCP public base URL"):
        create_server(config, options=MCPServerOptions(auth_mode="oauth"))


def test_create_server_oauth_mode_adds_tool_auth_metadata(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        _minimal_openapi_spec,
    )
    monkeypatch.setenv("NOCFO_MCP_JWKS_URI", "https://login.nocfo.io/jwks.json")

    server = create_server(
        config,
        options=MCPServerOptions(
            auth_mode="oauth",
            mcp_base_url="https://mcp.nocfo.io",
            required_scopes=("read",),
        ),
    )
    tools = asyncio.run(server.list_tools())
    assert len(tools) == 1
    meta = tools[0].meta or {}
    assert meta["mcp/www_authenticate"] == "Bearer"
    assert meta["securitySchemes"][0]["type"] == "oauth2"
    assert meta["securitySchemes"][0]["scopes"] == ["read"]
