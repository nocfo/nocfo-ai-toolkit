"""Runtime helpers for curated tools."""

from __future__ import annotations

from fastmcp.server.dependencies import get_context

from nocfo_toolkit.mcp.curated.client import CuratedNocfoClient

_CURATED_CLIENT_ATTR = "_nocfo_curated_client"
_CURATED_SKIP_CONFIRMATION_ATTR = "_nocfo_skip_mutation_confirmation"


def attach_curated_client(server: object, client: CuratedNocfoClient) -> None:
    """Attach curated client to FastMCP server instance."""
    setattr(server, _CURATED_CLIENT_ATTR, client)


def attach_confirmation_settings(server: object, *, skip_confirmation: bool) -> None:
    """Attach confirmation behavior settings to FastMCP server instance."""
    setattr(server, _CURATED_SKIP_CONFIRMATION_ATTR, bool(skip_confirmation))


def get_client() -> CuratedNocfoClient:
    try:
        context = get_context()
    except (LookupError, RuntimeError):
        context = None
    fastmcp = getattr(context, "fastmcp", None) if context is not None else None
    client = getattr(fastmcp, _CURATED_CLIENT_ATTR, None)
    if client is None:
        raise RuntimeError(
            "Curated MCP client is not configured. Initialize server first."
        )
    return client


def should_skip_mutation_confirmation(default: bool = False) -> bool:
    """Resolve whether mutation confirmations should be skipped in runtime."""
    try:
        context = get_context()
    except (LookupError, RuntimeError):
        return default
    fastmcp = getattr(context, "fastmcp", None)
    configured_value = getattr(fastmcp, _CURATED_SKIP_CONFIRMATION_ATTR, None)
    if isinstance(configured_value, bool):
        return configured_value
    return default


async def business_slug(business: str) -> str:
    return (await get_client().resolve_business(business)).slug
