"""NoCFO MCP server implementation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import AnyUrl
from fastmcp.server.providers.openapi.components import (
    OpenAPIResource,
    OpenAPIResourceTemplate,
)
from fastmcp.server.providers.openapi.routing import MCPType, RouteMap
from fastmcp.tools.tool import Tool

from nocfo_toolkit.config import AUTH_HEADER_SCHEME, ToolkitConfig
from nocfo_toolkit.mcp.auth import (
    MCPAuthOptions,
    JwtExchangeAuth,
    apply_tool_auth_metadata,
    build_remote_auth_provider,
)
from nocfo_toolkit.mcp.http_error_capture import capture_http_error_response
from nocfo_toolkit.mcp.invoice_app import register_invoice_app_capability
from nocfo_toolkit.mcp.middleware import MCPToolErrorMiddleware
from nocfo_toolkit.openapi import (
    MCP_RESOURCE_TAG,
    MCP_TOOL_TAG,
    filter_mcp_spec,
    load_openapi_spec,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Semantic mapping for MCP-tagged routes (see FastMCP OpenAPI route maps):
# https://gofastmcp.com/integrations/openapi#custom-route-maps
MCP_OPENAPI_ROUTE_MAPS: list[RouteMap] = [
    RouteMap(tags={MCP_RESOURCE_TAG}, mcp_type=MCPType.RESOURCE),
    RouteMap(tags={MCP_TOOL_TAG}, mcp_type=MCPType.TOOL),
    RouteMap(mcp_type=MCPType.EXCLUDE),
]

# Must match ``nocfo.spectacular_hooks.MCP_NAMESPACE_EXTENSION`` (set by ``mcp_extend_schema``).
X_MCP_NAMESPACE = "x-mcp-namespace"
_X_MCP_PREFIX = "x-mcp-"
X_NOCFO_MCP_SERVER_INSTRUCTIONS = "x-nocfo-mcp-server-instructions"


def _normalize_mcp_namespace_token(value: str) -> str:
    """Normalize backend ``MCPNamespace`` string (allows accidental human-readable input)."""
    normalized = value.strip()
    if not normalized:
        return ""
    normalized = normalized.replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", normalized)
    normalized = re.sub(r"[^a-zA-Z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_").lower()


def build_mcp_component_name(
    operation_id: str, extensions: dict[str, Any] | None
) -> str:
    """Build MCP name ``<x-mcp-namespace>_<operation_id_with_dots_as_underscores>``.

    Namespace is read from the OpenAPI operation extension ``x-mcp-namespace`` (set in
    the backend via ``mcp_extend_schema``). If missing, ``operation_id`` is
    returned unchanged.
    """
    if not operation_id or not str(operation_id).strip():
        return operation_id
    raw = (extensions or {}).get(X_MCP_NAMESPACE)
    if not isinstance(raw, str) or not raw.strip():
        return operation_id
    ns = _normalize_mcp_namespace_token(raw)
    if not ns:
        return operation_id
    # Avoid duplicating the namespace if operation_id already starts with it.
    # Example: operation_id "invoicing.contact.create" with ns "invoicing"
    # should become "invoicing_contact_create", not "invoicing_invoicing_contact_create".
    if operation_id.startswith(f"{ns}."):
        operation_id = operation_id[len(ns) + 1 :]
    return f"{ns}_{operation_id.replace('.', '_')}"


def _resource_uri_with_name(uri: str | AnyUrl, display_name: str) -> AnyUrl:
    """Keep ``resource://`` prefix and optional ``/{param}`` suffix; replace the name segment."""
    uri_str = str(uri)
    return AnyUrl(re.sub(r"^(resource://)([^/]+)", rf"\1{display_name}", uri_str))


def apply_mcp_namespace_names(route: Any, component: Any) -> None:
    """Apply ``x-mcp-namespace``-based MCP names to a tool, resource, or template.

    Used by :func:`create_server` and by tests that construct an
    :class:`OpenAPIProvider` with the same ``NoCFO`` naming policy.
    """
    if not getattr(route, "operation_id", None):
        return
    ext = getattr(route, "extensions", None) or {}
    display_name = build_mcp_component_name(route.operation_id, ext)
    if isinstance(component, Tool):
        component.name = display_name
        component.title = display_name
    elif isinstance(component, OpenAPIResource):
        component.name = display_name
        component.uri = _resource_uri_with_name(component.uri, display_name)
    elif isinstance(component, OpenAPIResourceTemplate):
        component.name = display_name
        component.uri_template = str(
            _resource_uri_with_name(component.uri_template, display_name)
        )


def apply_mcp_operation_metadata(route: Any, component: Any) -> None:
    """Attach OpenAPI ``x-mcp-*`` operation extensions to component metadata."""
    extensions = getattr(route, "extensions", None) or {}
    mcp_extensions = {
        key: value
        for key, value in extensions.items()
        if isinstance(key, str) and key.startswith(_X_MCP_PREFIX)
    }
    if not mcp_extensions:
        return

    meta: dict[str, Any] = dict(getattr(component, "meta", None) or {})
    nocfo_meta: dict[str, Any] = dict(meta.get("nocfo") or {})
    nocfo_meta["mcp"] = mcp_extensions
    meta["nocfo"] = nocfo_meta
    component.meta = meta


def _get_server_instructions(openapi_spec: dict[str, Any]) -> str | None:
    """Read backend-owned MCP server instructions from OpenAPI root extensions."""
    instructions = openapi_spec.get(X_NOCFO_MCP_SERVER_INSTRUCTIONS)
    if not isinstance(instructions, str):
        return None
    cleaned = instructions.strip()
    return cleaned or None


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
    resolved_token = config.jwt_token or config.api_token
    if not resolved_token:
        raise RuntimeError(
            "Missing authentication token. Set NOCFO_JWT_TOKEN or NOCFO_API_TOKEN, "
            "or run `nocfo auth configure` before starting MCP server in PAT mode."
        )
    return httpx.AsyncClient(
        base_url=config.base_url,
        headers={"Authorization": f"{AUTH_HEADER_SCHEME} {resolved_token}"},
        timeout=timeout_seconds,
        event_hooks={"response": [capture_http_error_response]},
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
        event_hooks={"response": [capture_http_error_response]},
    )


def create_server(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> FastMCP:
    """Create an MCP server from NoCFO OpenAPI specification."""

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
    else:
        client = _create_pat_client(config, opts.timeout_seconds)
        server_auth = None

    spec = load_openapi_spec(base_url=config.base_url)
    filtered_spec = filter_mcp_spec(spec, mcp_tag="MCP")
    server_instructions = _get_server_instructions(spec)

    def component_mapper(route: Any, component: Any) -> None:
        apply_mcp_namespace_names(route, component)
        apply_mcp_operation_metadata(route, component)
        if opts.auth_mode == "oauth" and isinstance(
            component, (Tool, OpenAPIResource, OpenAPIResourceTemplate)
        ):
            apply_tool_auth_metadata(
                component,
                required_scopes=opts.required_scopes,
            )

    server = FastMCP.from_openapi(
        openapi_spec=filtered_spec,
        client=client,
        name=opts.name,
        instructions=server_instructions,
        auth=server_auth,
        middleware=[MCPToolErrorMiddleware()],
        route_maps=MCP_OPENAPI_ROUTE_MAPS,
        mcp_component_fn=component_mapper,
        validate_output=True,
    )
    # Additive invoice app capability layered on top of the existing OpenAPI tools.
    register_invoice_app_capability(server)
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
    server.run(transport="http", host=host, port=port, path=path)


async def run_server_async(
    config: ToolkitConfig,
    *,
    options: MCPServerOptions | None = None,
) -> None:
    """Async wrapper for environments requiring a coroutine entrypoint."""

    await asyncio.to_thread(run_server, config, options=options)
