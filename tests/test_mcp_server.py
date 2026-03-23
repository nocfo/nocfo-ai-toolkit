from __future__ import annotations

import pytest

from nocfo_toolkit.config import OutputFormat, TokenSource, ToolkitConfig
from nocfo_toolkit.mcp.server import create_server
from nocfo_toolkit.openapi import filter_mcp_spec


def test_filter_mcp_spec_keeps_only_mcp_tagged_operations() -> None:
    spec = {
        "paths": {
            "/v1/a/": {
                "get": {"tags": ["MCP"]},
                "post": {"tags": ["Internal"]},
            },
            "/v1/b/": {
                "get": {"tags": ["Public"]},
            },
        }
    }

    filtered = filter_mcp_spec(spec)

    assert "/v1/a/" in filtered["paths"]
    assert "get" in filtered["paths"]["/v1/a/"]
    assert "post" not in filtered["paths"]["/v1/a/"]
    assert "/v1/b/" not in filtered["paths"]


def test_create_server_requires_token() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
    )

    with pytest.raises(RuntimeError, match="Missing authentication token"):
        create_server(config)


def test_create_server_accepts_jwt_without_pat(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        lambda *, base_url: {
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
        },
    )

    server = create_server(config)
    assert server is not None
