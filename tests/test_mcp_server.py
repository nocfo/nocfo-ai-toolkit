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

    with pytest.raises(RuntimeError, match="Missing API token"):
        create_server(config)
