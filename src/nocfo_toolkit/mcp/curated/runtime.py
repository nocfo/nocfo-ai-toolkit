"""Runtime helpers for curated tools."""

from __future__ import annotations

from fastmcp.server.dependencies import get_context

from nocfo_toolkit.mcp.curated.client import CuratedNocfoClient

_CURATED_CLIENT_ATTR = "_nocfo_curated_client"


def attach_curated_client(server: object, client: CuratedNocfoClient) -> None:
    """Attach curated client to FastMCP server instance."""
    setattr(server, _CURATED_CLIENT_ATTR, client)


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


async def business_slug(business: str) -> str:
    return (await get_client().resolve_business(business)).slug
