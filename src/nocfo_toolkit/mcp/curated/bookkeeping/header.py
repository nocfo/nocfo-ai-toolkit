"""Bookkeeping account header MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.tool_access import ToolTag
from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    HeaderIdInput,
    HeaderListInput,
    HeaderPayloadInput,
    HeaderSummary,
    ListEnvelope,
    dump_model_from_backend,
)


header_fields = ("id", "name", "type", "parent_id", "parent_ids", "level")


@tool(
    name="bookkeeping_headers_list",
    tags={ToolTag.READ_ONLY.value},
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
    tags={ToolTag.READ_ONLY.value},
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
    description="Create an account header when account headers are enabled for the business.",
)
async def bookkeeping_header_create(params: HeaderPayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/business/{slug}/header/"
    result = await get_client().request(
        "POST",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(HeaderSummary, result)
