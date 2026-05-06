"""NoCFO MCP server implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx
import uvicorn
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
from nocfo_toolkit.mcp.middleware import MCPToolAccessMiddleware, MCPToolErrorMiddleware
from nocfo_toolkit.mcp.search import NocfoBM25SearchTransform
from nocfo_toolkit.mcp.tool_access import (
    ToolAccessProfile,
    request_tool_access_profile,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

MCP_RUNTIME_CONTRACT_HEADER = "X-Nocfo-MCP-Contract"
MCP_RUNTIME_CONTRACT_VALUE = "1"
MCP_CLIENT_HEADER = "x-nocfo-client"
MCP_DEFAULT_CLIENT = "nocfo-mcp"
READ_ONLY_PATH_SEGMENT = "read"
WRITE_PATH_SEGMENT = "write"


def _normalize_http_path(path: str) -> str:
    return f"/{(path or '/').strip('/')}"


def _append_segment(base_path: str, segment: str) -> str:
    if base_path == "/":
        return f"/{segment}"
    return f"{base_path}/{segment}"


def _oauth_protected_resource_path(mcp_path: str) -> str:
    if mcp_path == "/":
        return "/.well-known/oauth-protected-resource/"
    return f"/.well-known/oauth-protected-resource{mcp_path}"


@dataclass(frozen=True)
class SplitHTTPPaths:
    base_path: str
    read_path: str
    write_path: str
    oauth_base_path: str
    oauth_read_path: str
    oauth_write_path: str


def _split_http_paths(base_path: str) -> SplitHTTPPaths:
    normalized_base_path = _normalize_http_path(base_path)
    read_path = _append_segment(normalized_base_path, READ_ONLY_PATH_SEGMENT)
    write_path = _append_segment(normalized_base_path, WRITE_PATH_SEGMENT)
    return SplitHTTPPaths(
        base_path=normalized_base_path,
        read_path=read_path,
        write_path=write_path,
        oauth_base_path=_oauth_protected_resource_path(normalized_base_path),
        oauth_read_path=_oauth_protected_resource_path(read_path),
        oauth_write_path=_oauth_protected_resource_path(write_path),
    )


class SplitPathASGIAdapter:
    """Expose /read and /write aliases while serving one FastMCP app."""

    def __init__(self, app: Any, paths: SplitHTTPPaths) -> None:
        self._app = app
        self._paths = paths

    def _resolve_profile_mapping(self, path: str) -> tuple[str, ToolAccessProfile]:
        if path == self._paths.read_path:
            return self._paths.base_path, ToolAccessProfile.READ
        if path == self._paths.write_path:
            return self._paths.base_path, ToolAccessProfile.WRITE
        if path == self._paths.oauth_read_path:
            return self._paths.oauth_base_path, ToolAccessProfile.READ
        if path == self._paths.oauth_write_path:
            return self._paths.oauth_base_path, ToolAccessProfile.WRITE
        if path == self._paths.base_path:
            return self._paths.base_path, ToolAccessProfile.ALL
        if path == self._paths.oauth_base_path:
            return self._paths.oauth_base_path, ToolAccessProfile.ALL
        return path, ToolAccessProfile.ALL

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        original_path = str(scope.get("path") or "")
        rewritten_path, profile = self._resolve_profile_mapping(original_path)
        with request_tool_access_profile(profile):
            if rewritten_path == original_path:
                await self._app(scope, receive, send)
                return
            rewritten_scope = dict(scope)
            rewritten_scope["path"] = rewritten_path
            rewritten_scope["raw_path"] = rewritten_path.encode("utf-8")
            await self._app(rewritten_scope, receive, send)


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
    split_endpoints_enabled: bool = False


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
        middleware=[MCPToolAccessMiddleware(), MCPToolErrorMiddleware()],
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
    normalized_path = _normalize_http_path(path)
    if opts.split_endpoints_enabled:
        paths = _split_http_paths(normalized_path)
        app = server.http_app(path=paths.base_path, stateless_http=opts.stateless_http)
        split_app = SplitPathASGIAdapter(app, paths)
        uvicorn.run(split_app, host=host, port=port)
        return
    server.run(
        transport="http",
        host=host,
        port=port,
        path=normalized_path,
        stateless_http=opts.stateless_http,
    )


async def run_server_async(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> None:
    """Async wrapper for environments requiring a coroutine entrypoint."""

    await asyncio.to_thread(run_server, config, options=options)
