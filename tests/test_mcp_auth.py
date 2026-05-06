from __future__ import annotations

import asyncio
import base64
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from nocfo_toolkit.mcp.auth import (
    JwtExchangeAuth,
    MCPAuthConfigurationError,
    PassthroughAuth,
)
from nocfo_toolkit.mcp.server import (
    MCPServerOptions,
    _create_pat_client,
    create_server,
)
from nocfo_toolkit.config import OutputFormat, TokenSource, ToolkitConfig


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


def test_jwt_exchange_auth_dedupes_parallel_exchange(monkeypatch) -> None:
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
            if exchange_calls["count"] > 1:
                raise AssertionError("JWT exchange should be deduped across workers")
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
            await asyncio.gather(
                client.get("/v1/businesses/"), client.get("/v1/accounts/")
            )

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


def test_jwt_exchange_auth_surfaces_exchange_error_detail(monkeypatch) -> None:
    def fake_access_token():
        return SimpleNamespace(
            token="incoming-bearer",
            claims={"sub": "user-1"},
        )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/jwt/":
            return httpx.Response(401, json={"detail": "invalid_token"})
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
            await client.get("/v1/businesses/")

    with pytest.raises(
        RuntimeError,
        match="incoming bearer token is missing or invalid. Reason: invalid_token",
    ):
        asyncio.run(run())


def test_passthrough_auth_forwards_incoming_authorization_header(monkeypatch) -> None:
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.auth.get_http_headers",
        lambda include=None: {"authorization": "Bearer incoming-jwt"},
    )
    auth = PassthroughAuth()

    async def run() -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"auth": request.headers.get("Authorization")},
            )
        )
        async with httpx.AsyncClient(
            base_url="https://api.example.com",
            transport=transport,
            auth=auth,
        ) as client:
            response = await client.get("/v1/businesses/")
            assert response.status_code == 200
            assert response.json()["auth"] == "Bearer incoming-jwt"

    asyncio.run(run())


def test_passthrough_auth_forwards_incoming_x_nocfo_client_header(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.auth.get_http_headers",
        lambda include=None: {
            "authorization": "Bearer incoming-jwt",
            "x-nocfo-client": "my-agent/2.0",
        },
    )
    auth = PassthroughAuth()

    async def run() -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "auth": request.headers.get("Authorization"),
                    "x_nocfo_client": request.headers.get("x-nocfo-client"),
                },
            )
        )
        async with httpx.AsyncClient(
            base_url="https://api.example.com",
            transport=transport,
            auth=auth,
        ) as client:
            response = await client.get("/v1/businesses/")
            assert response.status_code == 200
            assert response.json()["auth"] == "Bearer incoming-jwt"
            assert response.json()["x_nocfo_client"] == "my-agent/2.0"

    asyncio.run(run())


def test_passthrough_auth_requires_authorization_header(monkeypatch) -> None:
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.auth.get_http_headers",
        lambda include=None: {},
    )
    auth = PassthroughAuth()

    async def run() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        async with httpx.AsyncClient(
            base_url="https://api.example.com",
            transport=transport,
            auth=auth,
        ) as client:
            await client.get("/v1/businesses/")

    with pytest.raises(RuntimeError, match="Missing Authorization header"):
        asyncio.run(run())


def test_create_server_oauth_mode_requires_public_base_url(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
    )

    with pytest.raises(MCPAuthConfigurationError, match="Missing MCP public base URL"):
        create_server(config, options=MCPServerOptions(auth_mode="oauth"))


def test_create_server_oauth_mode_uses_curated_tools_without_permission_metadata(
    monkeypatch,
) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
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
    resources = asyncio.run(server.list_resources())
    names = {tool.name for tool in tools}
    assert "common_current_business_retrieve" in names
    assert "bookkeeping_document_create" in names
    assert len(resources) == 0
    for component in tools[:5]:
        meta = component.meta or {}
        assert "mcp/www_authenticate" not in meta
        assert "securitySchemes" not in meta


def test_create_pat_client_prefers_jwt_token() -> None:
    config = ToolkitConfig(
        api_token="pat-token",
        token_source=TokenSource.ENV,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-token",
    )

    client = _create_pat_client(config, timeout_seconds=5.0)
    try:
        assert client.headers["Authorization"] == "Token jwt-token"
    finally:
        asyncio.run(client.aclose())


def test_create_pat_client_falls_back_to_pat() -> None:
    config = ToolkitConfig(
        api_token="pat-token",
        token_source=TokenSource.ENV,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token=None,
    )

    client = _create_pat_client(config, timeout_seconds=5.0)
    try:
        assert client.headers["Authorization"] == "Token pat-token"
    finally:
        asyncio.run(client.aclose())


def test_create_pat_client_requires_jwt_or_pat() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token=None,
    )

    with pytest.raises(RuntimeError, match="Missing authentication token"):
        _create_pat_client(config, timeout_seconds=5.0)
