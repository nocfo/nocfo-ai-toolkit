"""Constants and docs MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.instructions import BLUEPRINT_GUIDE, GLOSSARY
from nocfo_toolkit.mcp.curated.schemas import (
    ConstantsKind,
    ConstantsRetrieveInput,
    DocsKind,
    DocsRetrieveInput,
    ItemsResponse,
    TextResourceResponse,
    dump_model,
)


@tool(
    name="constants_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve constants payloads used by accounting workflows. Use kind=vat_codes or kind=vat_rates.",
)
async def constants_retrieve(params: ConstantsRetrieveInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    if args.kind == ConstantsKind.vat_codes:
        result = await get_client().request(
            "GET", f"/v1/business/{slug}/constants/vat_codes/", business_slug=slug
        )
        return {
            "kind": args.kind.value,
            "items": dump_model(
                ItemsResponse(items=result if isinstance(result, list) else [])
            )["items"],
        }
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/constants/vat_rates/",
        params={"date_at": args.date_at},
        business_slug=slug,
    )
    return {
        "kind": args.kind.value,
        "data": result if isinstance(result, dict) else {"items": result},
    }


@tool(
    name="docs_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve concise NoCFO MCP guidance docs by kind=blueprint or kind=glossary.",
)
async def docs_retrieve(params: DocsRetrieveInput) -> dict[str, Any]:
    if params.kind == DocsKind.blueprint:
        return {
            "kind": params.kind.value,
            "content": dump_model(TextResourceResponse(content=BLUEPRINT_GUIDE))[
                "content"
            ],
        }
    return {
        "kind": params.kind.value,
        "content": dump_model(TextResourceResponse(content=GLOSSARY))["content"],
    }
