"""Common/user/business MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.curated.confirmation import confirm_mutation
from nocfo_toolkit.mcp.curated.runtime import get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BusinessContextInput,
    BusinessSummary,
    ListEnvelope,
    PaginationInput,
    PayloadOnlyInput,
    ResolvedBusiness,
    UserSummary,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="common_current_business_retrieve",
    description="Resolve the effective NoCFO business. Use business='current' by default in business-scoped tools.",
    output_schema=ResolvedBusiness.model_json_schema(),
)
async def common_current_business_retrieve(
    params: BusinessContextInput,
) -> dict[str, Any]:
    args = params
    return dump_model(await get_client().resolve_business(args.business))


@tool(
    name="common_accessible_businesses_list",
    description="List businesses accessible to the authenticated user for choosing business scope.",
    output_schema=ListEnvelope[BusinessSummary].model_json_schema(),
)
async def common_accessible_businesses_list(
    params: PaginationInput,
) -> dict[str, Any]:
    args = params
    return await get_client().list_page(
        "/v1/business/",
        limit=args.limit,
        cursor=args.cursor,
        item_model=BusinessSummary,
    )


@tool(
    name="common_user_retrieve",
    description="Retrieve the authenticated user profile.",
)
async def common_user_retrieve() -> dict[str, Any]:
    payload = await get_client().request("GET", "/v1/user/")
    return dump_model_from_backend(UserSummary, payload)


@tool(
    name="common_user_update",
    description="Update basic authenticated user profile fields.",
)
async def common_user_update(params: PayloadOnlyInput) -> dict[str, Any]:
    args = params
    path = "/v1/user/"
    await confirm_mutation(
        business="current",
        tool_name="common_user_update",
        target_resource={"type": "user", "id": "current"},
        parameters=args.payload,
    )
    result = await get_client().request("PATCH", path, json_body=args.payload)
    return dump_model_from_backend(UserSummary, result)
