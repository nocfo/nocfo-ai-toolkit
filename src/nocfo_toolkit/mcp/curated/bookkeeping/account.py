"""Bookkeeping account MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.tool_access import ToolTag
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    AccountActionInput,
    AccountListItem,
    AccountListInput,
    AccountNumberInput,
    AccountPayloadInput,
    AccountRetrieveInput,
    AccountSummary,
    ActionResponse,
    DeletedResponse,
    ListEnvelope,
    PayloadInput,
    dump_model,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle


account_fields = (
    "number",
    "name",
    "type",
    "description",
    "is_shown",
    "is_used",
    "balance",
    "header_id",
    "header_path",
    "default_vat_code",
    "default_vat_rate",
)


@tool(
    name="bookkeeping_accounts_list",
    tags={ToolTag.READ_ONLY.value},
    description="List bookkeeping accounts by account number, account range, name query, type, usage, or visibility. Use account numbers when talking with users.",
    output_schema=ListEnvelope[AccountListItem].model_json_schema(),
)
async def bookkeeping_accounts_list(params: AccountListInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/business/{slug}/account/",
        params=args.query_params(),
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        fields=account_fields,
        item_model=AccountListItem,
        handle_resource="bookkeeping_account",
        usage_hint="For account number lookup (e.g. 1910), set number filter and then use tool_handle with bookkeeping_account_retrieve.",
    )


@tool(
    name="bookkeeping_account_retrieve",
    tags={ToolTag.READ_ONLY.value},
    description="Retrieve one account from bookkeeping_accounts_list.items[].tool_handle.",
)
async def bookkeeping_account_retrieve(
    params: AccountRetrieveInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    account_id = decode_tool_handle(
        args.tool_handle,
        expected_resource="bookkeeping_account",
    )
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/account/{account_id}/",
        business_slug=slug,
    )
    return dump_model_from_backend(AccountSummary, result)


@tool(
    name="bookkeeping_account_create",
    description="Create a bookkeeping account. Use account numbers and account names that match the user request.",
)
async def bookkeeping_account_create(params: PayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/business/{slug}/account/"
    result = await get_client().request(
        "POST",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(AccountSummary, result)


@tool(
    name="bookkeeping_account_update",
    description="Update a bookkeeping account selected by account_number.",
)
async def bookkeeping_account_update(params: AccountPayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    account_id = await get_client().resolve_id(
        f"/v1/business/{slug}/account/",
        lookup_field="number",
        lookup_value=args.account_number,
        business_slug=slug,
    )
    path = f"/v1/business/{slug}/account/{account_id}/"
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(AccountSummary, result)


@tool(
    name="bookkeeping_account_delete",
    description="Delete a bookkeeping account selected by account_number.",
)
async def bookkeeping_account_delete(params: AccountNumberInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    account_id = await get_client().resolve_id(
        f"/v1/business/{slug}/account/",
        lookup_field="number",
        lookup_value=args.account_number,
        business_slug=slug,
    )
    path = f"/v1/business/{slug}/account/{account_id}/"
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(account_number=args.account_number))


@tool(
    name="bookkeeping_account_action",
    description="Show or hide a bookkeeping account selected by account_number.",
)
async def bookkeeping_account_action(params: AccountActionInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    account_id = await get_client().resolve_id(
        f"/v1/business/{slug}/account/",
        lookup_field="number",
        lookup_value=args.account_number,
        business_slug=slug,
    )
    path = f"/v1/business/{slug}/account/{account_id}/{args.action.value}/"
    await get_client().request(
        "POST",
        path,
        business_slug=slug,
    )
    return dump_model(
        ActionResponse(account_number=args.account_number, action=args.action.value)
    )
