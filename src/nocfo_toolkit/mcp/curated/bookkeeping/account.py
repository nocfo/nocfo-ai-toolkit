"""Bookkeeping account MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    AccountActionItem,
    AccountActionsInput,
    AccountListItem,
    AccountListInput,
    AccountNumbersInput,
    AccountRetrieveInput,
    AccountSummary,
    AccountUpdateItem,
    AccountUpdatesInput,
    ActionResponse,
    BatchResponse,
    DeletedResponse,
    ListEnvelope,
    PayloadsInput,
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
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List bookkeeping accounts by account number, account range, name query, type, usage, or visibility. Use this first to ground exact account numbers/tool_handles before updating, deleting, showing, or hiding accounts. Use account numbers when talking with users.",
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
        usage_hint=(
            "For account number lookup (e.g. 1910), set number filter and then use tool_handle with "
            "bookkeeping_account_retrieve. Before update/delete/show/hide actions, ground the exact targets here "
            "first and then batch the confirmed account numbers into one mutation call."
        ),
    )


@tool(
    name="bookkeeping_account_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve one account from bookkeeping_accounts_list.items[].tool_handle. Use this to verify an account before updating, deleting, showing, or hiding it.",
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
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Create one or more bookkeeping accounts in a single call — pass each new account as an entry in payloads. Use account numbers and names that match the user request; pass the account name as `name` (it is applied to every supported language).",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_account_create(params: PayloadsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/business/{slug}/account/"

    async def _create(payload: dict[str, Any]) -> dict[str, Any]:
        result = await get_client().request(
            "POST",
            path,
            json_body=_resolve_account_payload(payload),
            business_slug=slug,
        )
        return dump_model_from_backend(AccountSummary, result)

    return await run_batch(
        params.payloads,
        _create,
        label=lambda payload: payload.get("number") or payload.get("name"),
    )


@tool(
    name="bookkeeping_account_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Update one or more bookkeeping accounts in a single confirmed call — pass each update (account_number + the fields to change for THAT account) as an entry in updates. To rename, set `name` in the payload (it is applied to every supported language). Different accounts can get different changes in one call (e.g. rename account 1910 to X and 2000 to Y). Ground the exact account numbers first.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_account_update(
    params: AccountUpdatesInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(item: AccountUpdateItem) -> dict[str, Any]:
        account_id = await get_client().resolve_id(
            f"/v1/business/{slug}/account/",
            lookup_field="number",
            lookup_value=item.account_number,
            business_slug=slug,
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/account/{account_id}/",
            json_body=_resolve_account_payload(item.payload),
            business_slug=slug,
        )
        return dump_model_from_backend(AccountSummary, result)

    return await run_batch(
        params.updates, _update, label=lambda item: item.account_number
    )


# Backend account `name` is read-only; the writable field is `name_translations`
# (a list of {key, value} per language). The display name falls back across
# languages, so applying the requested name to every supported language renames
# the account everywhere.
_ACCOUNT_NAME_LANGUAGES = ("fi", "sv", "en", "de")


def _resolve_account_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a friendly account `name` to the backend's `name_translations` shape."""
    body = dict(payload)
    translations = body.get("name_translations")
    name = body.pop("name", None)
    if isinstance(translations, dict):
        body["name_translations"] = [
            {"key": key, "value": value} for key, value in translations.items()
        ]
    elif translations is None and name is not None:
        body["name_translations"] = [
            {"key": lang, "value": name} for lang in _ACCOUNT_NAME_LANGUAGES
        ]
    return body


@tool(
    name="bookkeeping_account_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more bookkeeping accounts in a single call — pass every target in account_numbers. Ground the exact account numbers first with bookkeeping_accounts_list and/or bookkeeping_account_retrieve, then batch all confirmed targets into one call. Never call this with guessed placeholders or an empty target set. Prefer one batched call over repeated single-target calls (each call needs its own confirmation).",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_account_delete(params: AccountNumbersInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(account_number: int) -> dict[str, Any]:
        account_id = await get_client().resolve_id(
            f"/v1/business/{slug}/account/",
            lookup_field="number",
            lookup_value=account_number,
            business_slug=slug,
        )
        await get_client().request(
            "DELETE",
            f"/v1/business/{slug}/account/{account_id}/",
            business_slug=slug,
        )
        return dump_model(DeletedResponse(account_number=account_number))

    return await run_batch(params.account_numbers, _delete)


@tool(
    name="bookkeeping_account_action",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Show or hide one or more bookkeeping accounts in a single confirmed call — pass each action (account_number + the action for THAT account) as an entry in actions. Different accounts can get different actions (e.g. show some and hide others) in one call. First obtain the exact account numbers from bookkeeping_accounts_list or bookkeeping_account_retrieve.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_account_action(
    params: AccountActionsInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _act(item: AccountActionItem) -> dict[str, Any]:
        account_id = await get_client().resolve_id(
            f"/v1/business/{slug}/account/",
            lookup_field="number",
            lookup_value=item.account_number,
            business_slug=slug,
        )
        action_value = getattr(item.action, "value", item.action)
        await get_client().request(
            "POST",
            f"/v1/business/{slug}/account/{account_id}/{action_value}/",
            business_slug=slug,
        )
        return dump_model(
            ActionResponse(account_number=item.account_number, action=action_value)
        )

    return await run_batch(params.actions, _act, label=lambda item: item.account_number)
