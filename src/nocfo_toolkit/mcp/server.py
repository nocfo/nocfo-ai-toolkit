"""NoCFO MCP server implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from nocfo_toolkit.config import AUTH_HEADER_SCHEME, ToolkitConfig
from nocfo_toolkit.openapi import filter_mcp_spec, load_openapi_spec

if TYPE_CHECKING:
    from fastmcp import FastMCP


@dataclass(frozen=True)
class MCPServerOptions:
    """MCP server configuration options."""

    name: str = "NoCFO"
    timeout_seconds: float = 30.0


def create_server(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> FastMCP:
    """Create an MCP server from NoCFO OpenAPI specification."""

    if not config.api_token:
        raise RuntimeError(
            "Missing API token. Set NOCFO_API_TOKEN or run `nocfo auth configure` "
            "before starting MCP server."
        )

    from fastmcp import FastMCP
    from fastmcp.server.openapi import MCPType, RouteMap

    opts = options or MCPServerOptions()
    spec = load_openapi_spec(base_url=config.base_url)
    filtered_spec = filter_mcp_spec(spec, mcp_tag="MCP")

    client = httpx.AsyncClient(
        base_url=config.base_url,
        headers={"Authorization": f"{AUTH_HEADER_SCHEME} {config.api_token}"},
        timeout=opts.timeout_seconds,
    )

    return FastMCP.from_openapi(
        openapi_spec=filtered_spec,
        client=client,
        name=opts.name,
        route_maps=[
            RouteMap(tags={"MCP"}, mcp_type=MCPType.TOOL),
            RouteMap(mcp_type=MCPType.EXCLUDE),
        ],
        validate_output=False,
    )


def run_server(config: ToolkitConfig) -> None:
    """Run NoCFO MCP server over stdio transport."""

    server = create_server(config)
    server.run()


async def run_server_async(config: ToolkitConfig) -> None:
    """Async wrapper for environments requiring a coroutine entrypoint."""

    await asyncio.to_thread(run_server, config)
