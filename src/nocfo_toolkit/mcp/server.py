"""NoCFO MCP server implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp.tools.tool import Tool

from nocfo_toolkit.config import AUTH_HEADER_SCHEME, ToolkitConfig
from nocfo_toolkit.mcp.auth import (
    MCPAuthOptions,
    JwtExchangeAuth,
    apply_tool_auth_metadata,
    build_remote_auth_provider,
)
from nocfo_toolkit.openapi import filter_mcp_spec, load_openapi_spec

if TYPE_CHECKING:
    from fastmcp import FastMCP


@dataclass(frozen=True)
class MCPServerOptions:
    """MCP server configuration options."""

    name: str = "NoCFO"
    timeout_seconds: float = 30.0
    auth_mode: Literal["pat", "oauth"] = "pat"
    mcp_base_url: str | None = None
    jwt_exchange_path: str = "/auth/jwt/"
    token_refresh_skew_seconds: int = 60
    required_scopes: tuple[str, ...] = ()


def _create_pat_client(
    config: ToolkitConfig, timeout_seconds: float
) -> httpx.AsyncClient:
    if not config.api_token:
        raise RuntimeError(
            "Missing API token. Set NOCFO_API_TOKEN or run `nocfo auth configure` "
            "before starting MCP server in PAT mode."
        )
    return httpx.AsyncClient(
        base_url=config.base_url,
        headers={"Authorization": f"{AUTH_HEADER_SCHEME} {config.api_token}"},
        timeout=timeout_seconds,
    )


def _create_oauth_client(
    config: ToolkitConfig,
    *,
    exchange_path: str,
    timeout_seconds: float,
    refresh_skew_seconds: int,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=config.base_url,
        auth=JwtExchangeAuth(
            exchange_path=exchange_path,
            refresh_skew_seconds=refresh_skew_seconds,
        ),
        timeout=timeout_seconds,
    )


def create_server(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> FastMCP:
    """Create an MCP server from NoCFO OpenAPI specification."""

    from fastmcp import FastMCP
    from fastmcp.server.providers.openapi.routing import MCPType, RouteMap

    opts = options or MCPServerOptions()
    spec = load_openapi_spec(base_url=config.base_url)
    filtered_spec = filter_mcp_spec(spec, mcp_tag="MCP")

    if opts.auth_mode == "oauth":
        client = _create_oauth_client(
            config,
            exchange_path=opts.jwt_exchange_path,
            timeout_seconds=opts.timeout_seconds,
            refresh_skew_seconds=opts.token_refresh_skew_seconds,
        )
        server_auth = build_remote_auth_provider(
            config=config,
            options=MCPAuthOptions(
                mode="oauth",
                mcp_base_url=opts.mcp_base_url,
                jwt_exchange_path=opts.jwt_exchange_path,
                token_refresh_skew_seconds=opts.token_refresh_skew_seconds,
                required_scopes=opts.required_scopes,
            ),
        )
    else:
        client = _create_pat_client(config, opts.timeout_seconds)
        server_auth = None

    def component_mapper(_: Any, component: Any) -> None:
        if opts.auth_mode != "oauth":
            return
        if isinstance(component, Tool):
            apply_tool_auth_metadata(
                component,
                required_scopes=opts.required_scopes,
            )

    return FastMCP.from_openapi(
        openapi_spec=filtered_spec,
        client=client,
        name=opts.name,
        auth=server_auth,
        route_maps=[
            RouteMap(tags={"MCP"}, mcp_type=MCPType.TOOL),
            RouteMap(mcp_type=MCPType.EXCLUDE),
        ],
        mcp_component_fn=component_mapper,
        validate_output=False,
    )


def run_server(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> None:
    """Run NoCFO MCP server over stdio transport."""

    server = create_server(config, options=options)
    server.run()


def run_http_server(
    config: ToolkitConfig,
    *,
    host: str = "0.0.0.0",  # nosec: B104
    port: int = 8000,
    path: str = "/mcp",
    options: MCPServerOptions | None = None,
) -> None:
    """Run NoCFO MCP server over streamable HTTP transport."""

    server = create_server(config, options=options)
    server.run(transport="http", host=host, port=port, path=path)


async def run_server_async(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> None:
    """Async wrapper for environments requiring a coroutine entrypoint."""

    await asyncio.to_thread(run_server, config, options=options)
