"""Bookkeeping account header MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    HeaderIdInput,
    HeaderListInput,
    HeaderSummary,
    ListEnvelope,
    PayloadsInput,
    dump_model_from_backend,
)


header_fields = ("id", "name", "type", "parent_id", "parent_ids", "level")


@tool(
    name="bookkeeping_headers_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List optional account header hierarchy. Returns feature_disabled if headers are not enabled.",
    output_schema=ListEnvelope[HeaderSummary].model_json_schema(),
)
async def bookkeeping_headers_list(params: HeaderListInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    try:
        return await get_client().list_page(
            f"/v1/business/{slug}/header/",
            params={"search": args.query},
            cursor=args.cursor,
            limit=args.limit,
            business_slug=slug,
            fields=header_fields,
            item_model=HeaderSummary,
        )
    except ToolError as exc:
        if "Header endpoints are disabled" in str(exc):
            raise_tool_error(
                "feature_disabled",
                "Account headers are not enabled for this business.",
                "Use bookkeeping_accounts_list and account numbers/types instead.",
                feature="account_headers",
                reason="country_not_supported",
            )
        raise


@tool(
    name="bookkeeping_header_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve one account header by header_id from bookkeeping_headers_list.",
)
async def bookkeeping_header_retrieve(params: HeaderIdInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/header/{args.header_id}/",
        business_slug=slug,
    )
    return dump_model_from_backend(HeaderSummary, result)


@tool(
    name="bookkeeping_header_create",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Create one or more account headers in a single call — pass each header as an entry in payloads. Available when account headers are enabled for the business.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_header_create(params: PayloadsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/business/{slug}/header/"

    async def _create(payload: dict[str, Any]) -> dict[str, Any]:
        result = await get_client().request(
            "POST", path, json_body=payload, business_slug=slug
        )
        return dump_model_from_backend(HeaderSummary, result)

    return await run_batch(
        params.payloads, _create, label=lambda payload: payload.get("name")
    )
