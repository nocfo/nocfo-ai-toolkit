from __future__ import annotations

import httpx
import pytest

from fastmcp.server.providers.openapi import OpenAPIProvider
from starlette.testclient import TestClient

from nocfo_toolkit.config import OutputFormat, TokenSource, ToolkitConfig
from nocfo_toolkit.mcp.server import (
    MCP_OPENAPI_ROUTE_MAPS,
    X_NOCFO_MCP_SERVER_INSTRUCTIONS,
    X_MCP_NAMESPACE,
    apply_mcp_operation_metadata,
    apply_mcp_namespace_names,
    build_mcp_component_name,
    create_server,
    MCPServerOptions,
    run_http_server,
    restore_openapi_output_schema,
)
from nocfo_toolkit.openapi import X_MCP_COMPONENT_TYPE, filter_mcp_spec


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


def test_create_server_uses_backend_server_instructions(monkeypatch) -> None:
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
            X_NOCFO_MCP_SERVER_INSTRUCTIONS: "Start from bootstrap.",
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

    class DummyServer:
        pass

    captured_kwargs: dict[str, object] = {}

    def _fake_from_openapi(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return DummyServer()

    monkeypatch.setattr("fastmcp.FastMCP.from_openapi", _fake_from_openapi)

    server = create_server(config)
    assert isinstance(server, DummyServer)
    assert captured_kwargs["instructions"] == "Start from bootstrap."


def test_oauth_protected_resource_metadata_strips_trailing_slashes(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "NOCFO_MCP_AUTHORIZATION_SERVERS",
        "http://localhost:8000/",
    )
    monkeypatch.setenv(
        "NOCFO_MCP_JWKS_URI",
        "http://localhost:8000/.well-known/jwks.json",
    )
    monkeypatch.setenv("NOCFO_MCP_JWT_ISSUER", "http://localhost:8000")
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        lambda *, base_url: {
            "openapi": "3.0.0",
            "info": {"title": "NoCFO", "version": "1.0.0"},
            "servers": [{"url": base_url}],
            "paths": {},
        },
    )

    server = create_server(
        ToolkitConfig(base_url="http://localhost:8000"),
        options=MCPServerOptions(
            auth_mode="oauth",
            mcp_base_url="http://127.0.0.1:8002",
        ),
    )
    app = server.http_app(path="/mcp")
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == "http://127.0.0.1:8002/mcp"
    assert metadata["authorization_servers"] == ["http://localhost:8000"]


def test_openapi_provider_maps_mcp_get_to_resources() -> None:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "NoCFO", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/v1/list/": {
                "get": {
                    "operationId": "bookkeeping.items.list",
                    "tags": ["MCP"],
                    X_MCP_NAMESPACE: "bookkeeping",
                    X_MCP_COMPONENT_TYPE: "resource",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/v1/item/{id}/": {
                "get": {
                    "operationId": "bookkeeping.item.retrieve",
                    "tags": ["MCP"],
                    X_MCP_NAMESPACE: "bookkeeping",
                    X_MCP_COMPONENT_TYPE: "resource",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/v1/item/": {
                "post": {
                    "operationId": "bookkeeping.item.create",
                    "tags": ["MCP"],
                    X_MCP_NAMESPACE: "bookkeeping",
                    "x-mcp-required-permissions": ["bookkeeping_editor"],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }
    filtered = filter_mcp_spec(spec)
    client = httpx.AsyncClient(base_url="https://api.example.com")

    def _apply_component_mcp_metadata(route, component) -> None:
        apply_mcp_namespace_names(route, component)
        apply_mcp_operation_metadata(route, component)
        restore_openapi_output_schema(route, component)

    provider = OpenAPIProvider(
        openapi_spec=filtered,
        client=client,
        route_maps=MCP_OPENAPI_ROUTE_MAPS,
        mcp_component_fn=_apply_component_mcp_metadata,
        validate_output=False,
    )

    assert len(provider._tools) == 1
    create_tool = next(iter(provider._tools.values()))
    assert create_tool._route.operation_id == "bookkeeping.item.create"
    assert create_tool.name == "bookkeeping_item_create"
    assert create_tool.meta["nocfo"]["mcp"][X_MCP_NAMESPACE] == "bookkeeping"
    assert create_tool.meta["nocfo"]["mcp"]["x-mcp-required-permissions"] == [
        "bookkeeping_editor"
    ]
    assert len(provider._resources) == 2
    operation_ids = {
        resource._route.operation_id for resource in provider._resources.values()
    }
    assert "bookkeeping.items.list" in operation_ids
    assert "bookkeeping.item.retrieve" in operation_ids
    names = {resource.name for resource in provider._resources.values()}
    assert "bookkeeping_items_list" in names
    assert "bookkeeping_item_retrieve" in names
    first_resource = next(iter(provider._resources.values()))
    assert first_resource.meta["nocfo"]["mcp"][X_MCP_COMPONENT_TYPE] == "resource"
    assert len(provider._templates) == 0


def test_build_mcp_component_name_uses_operation_id_only() -> None:
    assert (
        build_mcp_component_name(
            "a.b.c",
            {X_MCP_NAMESPACE: "invoicing"},
        )
        == "a_b_c"
    )


def test_build_mcp_component_name_ignores_namespace_token() -> None:
    assert (
        build_mcp_component_name(
            "x.y",
            {X_MCP_NAMESPACE: "Balance Sheet"},
        )
        == "x_y"
    )


def test_build_mcp_component_name_fallback_when_extension_missing() -> None:
    assert (
        build_mcp_component_name(
            "bookkeeping.item.create",
            {},
        )
        == "bookkeeping_item_create"
    )


def test_build_mcp_component_name_fallback_when_no_extensions() -> None:
    assert build_mcp_component_name("foo.bar", None) == "foo_bar"


def test_filter_mcp_spec_prefers_backend_component_type_extension() -> None:
    spec = {
        "paths": {
            "/v1/non-get-as-resource/": {
                "post": {
                    "operationId": "bookkeeping.custom.retrieve",
                    "tags": ["MCP"],
                    X_MCP_COMPONENT_TYPE: "resource",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        }
    }

    filtered = filter_mcp_spec(spec)
    tags = filtered["paths"]["/v1/non-get-as-resource/"]["post"]["tags"]
    assert "MCP_RESOURCE" in tags
    assert "MCP_TOOL" not in tags


def test_run_http_server_forwards_stateless_http(monkeypatch) -> None:
    config = ToolkitConfig(base_url="http://localhost:8000")

    class DummyServer:
        def run(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    captured_kwargs: dict[str, object] = {}
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.create_server",
        lambda config, options=None: DummyServer(),
    )

    run_http_server(
        config,
        host="127.0.0.1",
        port=9000,
        path="/mcp",
        options=MCPServerOptions(stateless_http=True),
    )

    assert captured_kwargs["transport"] == "http"
    assert captured_kwargs["host"] == "127.0.0.1"
    assert captured_kwargs["port"] == 9000
    assert captured_kwargs["path"] == "/mcp"
    assert captured_kwargs["stateless_http"] is True
