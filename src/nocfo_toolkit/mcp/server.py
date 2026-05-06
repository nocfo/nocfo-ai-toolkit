"""NoCFO MCP server implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.providers import FileSystemProvider

from nocfo_toolkit.config import AUTH_HEADER_SCHEME, ToolkitConfig
from nocfo_toolkit.mcp.auth import (
    MCPAuthOptions,
    JwtExchangeAuth,
    PassthroughAuth,
    build_remote_auth_provider,
)
from nocfo_toolkit.mcp.curated import SERVER_INSTRUCTIONS
from nocfo_toolkit.mcp.curated.client import CuratedNocfoClient
from nocfo_toolkit.mcp.curated.runtime import (
    attach_confirmation_settings,
    attach_curated_client,
)
from nocfo_toolkit.mcp.http_error_capture import capture_http_error_response
from nocfo_toolkit.mcp.middleware import MCPToolErrorMiddleware
from nocfo_toolkit.mcp.search import NocfoBM25SearchTransform

if TYPE_CHECKING:
    from fastmcp import FastMCP

MCP_RUNTIME_CONTRACT_HEADER = "X-Nocfo-MCP-Contract"
MCP_RUNTIME_CONTRACT_VALUE = "1"
MCP_CLIENT_HEADER = "x-nocfo-client"
MCP_DEFAULT_CLIENT = "nocfo-mcp"


def _request_requires_mcp_runtime_contract_header(request: httpx.Request) -> bool:
    path = str(request.url.path or "").strip()
    return path.startswith("/v1/") and not path.startswith("/v1/mcp/")


async def _inject_mcp_runtime_contract_header(request: httpx.Request) -> None:
    if not _request_requires_mcp_runtime_contract_header(request):
        return
    request.headers.setdefault(
        MCP_RUNTIME_CONTRACT_HEADER,
        MCP_RUNTIME_CONTRACT_VALUE,
    )


async def _inject_mcp_client_header(
    request: httpx.Request, *, default_client: str
) -> None:
    incoming_headers = get_http_headers(include={MCP_CLIENT_HEADER})
    incoming_client = (incoming_headers.get(MCP_CLIENT_HEADER) or "").strip()
    if incoming_client:
        request.headers[MCP_CLIENT_HEADER] = incoming_client
        return
    request.headers[MCP_CLIENT_HEADER] = default_client


def _client_event_hooks(default_client: str) -> dict[str, list[Any]]:
    return {
        "request": [
            _inject_mcp_runtime_contract_header,
            lambda request: _inject_mcp_client_header(
                request, default_client=default_client
            ),
        ],
        "response": [capture_http_error_response],
    }


@dataclass(frozen=True)
class MCPServerOptions:
    """MCP server configuration options."""

    name: str = "NoCFO"
    timeout_seconds: float = 30.0
    auth_mode: Literal["pat", "oauth", "passthrough"] = "pat"
    mcp_base_url: str | None = None
    jwt_exchange_path: str = "/auth/jwt/"
    token_refresh_skew_seconds: int = 60
    required_scopes: tuple[str, ...] = ()
    stateless_http: bool = False
    tool_search: bool = False
    skip_confirmation: bool = False


def _create_pat_client(
    config: ToolkitConfig, timeout_seconds: float
) -> httpx.AsyncClient:
    resolved_token = config.jwt_token or config.api_token
    if not resolved_token:
        raise RuntimeError(
            "Missing authentication token. Set NOCFO_JWT_TOKEN or NOCFO_API_TOKEN, "
            "or run `nocfo auth configure` before starting MCP server in PAT mode."
        )
    default_client = config.nocfo_client or MCP_DEFAULT_CLIENT
    return httpx.AsyncClient(
        base_url=config.base_url,
        headers={"Authorization": f"{AUTH_HEADER_SCHEME} {resolved_token}"},
        timeout=timeout_seconds,
        event_hooks=_client_event_hooks(default_client),
    )


def _create_oauth_client(
    config: ToolkitConfig,
    *,
    exchange_path: str,
    timeout_seconds: float,
    refresh_skew_seconds: int,
) -> httpx.AsyncClient:
    default_client = config.nocfo_client or MCP_DEFAULT_CLIENT
    return httpx.AsyncClient(
        base_url=config.base_url,
        auth=JwtExchangeAuth(
            exchange_path=exchange_path,
            refresh_skew_seconds=refresh_skew_seconds,
        ),
        timeout=timeout_seconds,
        event_hooks=_client_event_hooks(default_client),
    )


def _create_passthrough_client(
    config: ToolkitConfig, timeout_seconds: float
) -> httpx.AsyncClient:
    default_client = config.nocfo_client or MCP_DEFAULT_CLIENT
    return httpx.AsyncClient(
        base_url=config.base_url,
        auth=PassthroughAuth(),
        timeout=timeout_seconds,
        event_hooks=_client_event_hooks(default_client),
    )


def create_server(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> FastMCP:
    """Create a curated workflow-oriented NoCFO MCP server."""

    from fastmcp import FastMCP

    opts = options or MCPServerOptions()

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
    elif opts.auth_mode == "passthrough":
        client = _create_passthrough_client(config, opts.timeout_seconds)
        server_auth = None
    else:
        client = _create_pat_client(config, opts.timeout_seconds)
        server_auth = None

    transforms: list[Any] = []
    if opts.tool_search:
        transforms.append(NocfoBM25SearchTransform(max_results=12))

    curated_client = CuratedNocfoClient(client, config)
    curated_provider_root = Path(__file__).resolve().parent / "curated"

    server = FastMCP(
        name=opts.name,
        instructions=SERVER_INSTRUCTIONS,
        auth=server_auth,
        middleware=[MCPToolErrorMiddleware()],
        providers=[FileSystemProvider(root=curated_provider_root)],
        transforms=transforms,
    )
    attach_curated_client(server, curated_client)
    attach_confirmation_settings(server, skip_confirmation=opts.skip_confirmation)
    return server


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
    opts = options or MCPServerOptions()
    server.run(
        transport="http",
        host=host,
        port=port,
        path=path,
        stateless_http=opts.stateless_http,
    )


async def run_server_async(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> None:
    """Async wrapper for environments requiring a coroutine entrypoint."""

    await asyncio.to_thread(run_server, config, options=options)
