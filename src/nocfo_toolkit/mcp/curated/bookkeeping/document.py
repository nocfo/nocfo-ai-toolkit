"""Bookkeeping document and entry MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.tool_access import ToolTag
from nocfo_toolkit.mcp.curated.confirmation import confirm_mutation
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    DocumentActionInput,
    DocumentDetail,
    DocumentListItem,
    DocumentListInput,
    DocumentNumberInput,
    DocumentRetrieveInput,
    DocumentSummary,
    EntryListInput,
    EntrySummary,
    DeletedResponse,
    AgentDocumentBlueprintPayload,
    AgentBlueprintEntryPayload,
    DocumentMutationInput,
    DocumentMutationPayload,
    DocumentNumberMutationInput,
    ListEnvelope,
    dump_model,
    dump_model_from_backend,
    dump_models,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle, items


@tool(
    name="bookkeeping_documents_list",
    tags={ToolTag.READ_ONLY.value},
    description="List bookkeeping documents by document number, dates, contact, tag, account number, workflow state, or query.",
    output_schema=ListEnvelope[DocumentListItem].model_json_schema(),
)
async def bookkeeping_documents_list(
    params: DocumentListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    query_params = args.query_params()
    account_id = None
    if args.account_number is not None:
        account_id = await get_client().resolve_id(
            f"/v1/business/{slug}/account/",
            lookup_field="number",
            lookup_value=args.account_number,
            business_slug=slug,
        )
    query_params.pop("account_number", None)
    query_params["account"] = account_id
    result = await get_client().list_page(
        f"/v1/business/{slug}/document/",
        params=query_params,
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=DocumentListItem,
        handle_resource="bookkeeping_document",
        usage_hint="Use document_number/date filters to browse periods (e.g. one month). For account filtering, prefer account_number. Then pass tool_handle to bookkeeping_document_retrieve for full details.",
    )
    return result


@tool(
    name="bookkeeping_document_retrieve",
    tags={ToolTag.READ_ONLY.value},
    description="Retrieve one bookkeeping document from bookkeeping_documents_list.items[].tool_handle. Includes blueprint/entry/relation workflow summaries.",
)
async def bookkeeping_document_retrieve(
    params: DocumentRetrieveInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document_id = decode_tool_handle(
        args.tool_handle,
        expected_resource="bookkeeping_document",
    )
    document = await document_by_id(slug, document_id)
    entries = await entries_for_document(slug, int(document["id"]))
    return dump_model(
        DocumentDetail.model_validate(
            {
                **document,
                "blueprint": document.get("blueprint"),
                "entry_summary": dump_models(EntrySummary, entries[:20]),
                "tag_ids": document.get("tag_ids"),
                "relations": document.get("relations"),
            }
        )
    )


@tool(
    name="bookkeeping_document_create",
    description="Create a bookkeeping document/business transaction. Blueprint is the editable posting plan; generated entries are returned for verification.",
)
async def bookkeeping_document_create(
    params: DocumentMutationInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    if not isinstance(args.payload.blueprint, dict):
        raise_tool_error(
            "invalid_request",
            "blueprint is required for bookkeeping_document_create.",
            "Provide payload.blueprint as an object with document posting fields.",
            status_code=400,
        )
    body = await resolve_document_payload(slug, args.payload, is_patch=False)
    path = f"/v1/business/{slug}/document/"
    await confirm_mutation(
        business=slug,
        tool_name="bookkeeping_document_create",
        target_resource={
            "type": "document",
            "id": str(body.get("number") or body.get("description") or "new"),
        },
        parameters=body,
    )
    created = await get_client().request(
        "POST",
        path,
        json_body=body,
        business_slug=slug,
    )
    document_id = int(created["id"])
    entries = await entries_for_document(slug, document_id)
    return dump_model(
        DocumentDetail.model_validate(
            {
                **created,
                "entry_summary": dump_models(EntrySummary, entries[:20]),
            }
        )
    )


@tool(
    name="bookkeeping_document_update",
    description="Update a document blueprint or metadata by document_number. This recalculates generated entries. If payload contains tag_names, those tags must already exist; create missing tags first with bookkeeping_tag_create.",
)
async def bookkeeping_document_update(
    params: DocumentNumberMutationInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    body = await resolve_document_payload(slug, args.payload, is_patch=True)
    path = f"/v1/business/{slug}/document/{document['id']}/"
    await confirm_mutation(
        business=slug,
        tool_name="bookkeeping_document_update",
        target_resource={
            "type": "document",
            "id": int(document["id"]),
        },
        parameters=body,
    )
    updated = await get_client().request(
        "PATCH",
        path,
        json_body=body,
        business_slug=slug,
    )
    entries = await entries_for_document(slug, int(document["id"]))
    return dump_model(
        DocumentDetail.model_validate(
            {
                **updated,
                "entry_summary": dump_models(EntrySummary, entries[:20]),
            }
        )
    )


@tool(
    name="bookkeeping_document_delete",
    description="Delete a bookkeeping document selected by document_number.",
)
async def bookkeeping_document_delete(
    params: DocumentNumberInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    path = f"/v1/business/{slug}/document/{document['id']}/"
    await confirm_mutation(
        business=slug,
        tool_name="bookkeeping_document_delete",
        target_resource={
            "type": "document",
            "id": int(document["id"]),
        },
    )
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(document_number=args.document_number))


@tool(
    name="bookkeeping_entries_list",
    tags={ToolTag.READ_ONLY.value},
    description="List realized journal entries for a document. Entries are generated from blueprint and are read-only in MCP.",
    output_schema=ListEnvelope[EntrySummary].model_json_schema(),
)
async def bookkeeping_entries_list(
    params: EntryListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    result = await get_client().list_page(
        f"/v1/business/{slug}/document/{document['id']}/entry/",
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=EntrySummary,
    )
    return result


@tool(
    name="bookkeeping_document_finalize_active_suggestion",
    description="Apply the active accounting suggestion for a draft document and finalize it.",
)
async def bookkeeping_document_finalize_active_suggestion(
    params: DocumentNumberInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    path = (
        f"/v1/mcp/business/{slug}/documents/{document['id']}/"
        "actions/finalize_active_suggestion/"
    )
    await confirm_mutation(
        business=slug,
        tool_name="bookkeeping_document_finalize_active_suggestion",
        target_resource={
            "type": "document",
            "id": int(document["id"]),
        },
    )
    result = await get_client().request(
        "POST",
        path,
        json_body={},
        business_slug=slug,
    )
    return dump_model_from_backend(DocumentSummary, result)


@tool(
    name="bookkeeping_document_action",
    description="Run a state action on a document: lock, unlock, flag, or unflag.",
)
async def bookkeeping_document_action(
    params: DocumentActionInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    path = f"/v1/business/{slug}/document/{document['id']}/action/{args.action.value}/"
    await confirm_mutation(
        business=slug,
        tool_name="bookkeeping_document_action",
        target_resource={
            "type": "document",
            "id": int(document["id"]),
        },
    )
    result = await get_client().request(
        "POST",
        path,
        business_slug=slug,
    )
    return dump_model_from_backend(
        DocumentSummary, result if isinstance(result, dict) else document
    )


async def document_by_number(slug: str, number: str) -> dict[str, Any]:
    payload = await get_client().request(
        "GET",
        f"/v1/business/{slug}/document/",
        params={"number": number, "page_size": 3},
        business_slug=slug,
    )
    candidates = items(payload)
    if len(candidates) != 1:
        raise_tool_error(
            "ambiguous_reference" if candidates else "not_found",
            f"Could not resolve document_number={number}.",
            "Use bookkeeping_documents_list to find the exact document.",
            candidates=[
                dump_model_from_backend(DocumentSummary, item) for item in candidates
            ],
        )
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/document/{candidates[0]['id']}/",
        business_slug=slug,
    )
    return result


async def document_by_id(slug: str, document_id: int) -> dict[str, Any]:
    return await get_client().request(
        "GET",
        f"/v1/business/{slug}/document/{document_id}/",
        business_slug=slug,
    )


async def entries_for_document(slug: str, document_id: int) -> list[dict[str, Any]]:
    payload = await get_client().request(
        "GET",
        f"/v1/business/{slug}/document/{document_id}/entry/",
        params={"page_size": 100},
        business_slug=slug,
    )
    return items(payload)


async def resolve_document_payload(
    slug: str,
    payload: DocumentMutationPayload,
    *,
    is_patch: bool,
) -> dict[str, Any]:
    client = get_client()
    body: dict[str, Any] = {}

    def include_field(name: str, value: Any) -> bool:
        if is_patch:
            return name in payload.model_fields_set
        return value is not None

    extra_payload = payload.model_extra or {}
    for key, value in extra_payload.items():
        if key in {"contact", "contact_id", "tag_names", "tag_ids", "blueprint"}:
            continue
        if is_patch or value is not None:
            body[key] = value

    contact = payload.contact
    contact_id = payload.contact_id
    contact_set = include_field("contact", contact)
    contact_id_set = include_field("contact_id", contact_id)
    if contact_set and contact_id_set:
        raise_tool_error(
            "invalid_request",
            "Provide only one of contact or contact_id.",
            "Use contact for exact contact name, or contact_id for numeric contact ID.",
            status_code=400,
        )

    if contact_set:
        if not isinstance(contact, str):
            raise_tool_error(
                "invalid_request",
                "contact must be a name string.",
                "Provide contact as an exact contact name.",
                status_code=400,
            )
        contact_name = contact.strip()
        if not contact_name:
            raise_tool_error(
                "invalid_request",
                "contact cannot be empty.",
                "Provide contact_id as numeric ID or contact as an exact contact name.",
                status_code=400,
            )
        body["contact_id"] = await client.resolve_id(
            f"/v1/business/{slug}/contacts/",
            lookup_field="name",
            lookup_value=contact_name,
            search_param="search",
            business_slug=slug,
        )
    elif contact_id_set:
        if isinstance(contact_id, str):
            trimmed_id = contact_id.strip()
            if not trimmed_id:
                raise_tool_error(
                    "invalid_request",
                    "contact_id cannot be empty.",
                    "Provide contact_id as a numeric ID.",
                    status_code=400,
                )
            if not trimmed_id.isdigit():
                raise_tool_error(
                    "invalid_request",
                    "contact_id must be numeric when provided as a string.",
                    "Use contact for contact name lookups.",
                    status_code=400,
                )
            body["contact_id"] = int(trimmed_id)
        else:
            body["contact_id"] = contact_id

    tag_names_set = include_field("tag_names", payload.tag_names)
    tag_ids_set = include_field("tag_ids", payload.tag_ids)
    if tag_ids_set:
        body["tag_ids"] = payload.tag_ids
    elif tag_names_set:
        tag_ids = []
        for tag_name in payload.tag_names or []:
            tag_ids.append(
                await client.resolve_id(
                    f"/v1/business/{slug}/tags/",
                    lookup_field="name",
                    lookup_value=tag_name,
                    search_param="search",
                    business_slug=slug,
                )
            )
        body["tag_ids"] = tag_ids

    blueprint_set = include_field("blueprint", payload.blueprint)
    if blueprint_set:
        if isinstance(payload.blueprint, dict):
            body["blueprint"] = await resolve_blueprint(slug, payload.blueprint)
        else:
            body["blueprint"] = payload.blueprint

    return body


async def resolve_blueprint(
    slug: str,
    value: dict[str, Any],
) -> dict[str, Any]:
    def rows(container: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key in ("debet_entries", "credit_entries", "expense_entries"):
            items = container.get(key)
            if isinstance(items, list):
                result.extend(item for item in items if isinstance(item, dict))
        return result

    AgentDocumentBlueprintPayload.model_validate(value)
    blueprint = dict(value)
    blueprint["debet_account_id"] = await _resolve_account_id(
        slug,
        account_id=blueprint.get("debet_account_id"),
        account_number=blueprint.get("debet_account_number"),
    )
    blueprint["credit_account_id"] = await _resolve_account_id(
        slug,
        account_id=blueprint.get("credit_account_id"),
        account_number=blueprint.get("credit_account_number"),
    )
    blueprint.pop("debet_account_number", None)
    blueprint.pop("credit_account_number", None)
    for row in rows(blueprint):
        AgentBlueprintEntryPayload.model_validate(row)
        normalized_row = dict(row)
        normalized_row["account_id"] = await _resolve_account_id(
            slug,
            account_id=normalized_row.get("account_id"),
            account_number=normalized_row.get("account_number"),
        )
        normalized_row.pop("account_number", None)
        row.clear()
        row.update(normalized_row)
    return blueprint


async def _resolve_account_id(
    slug: str,
    *,
    account_id: int | str | None,
    account_number: int | str | None,
) -> int | None:
    client = get_client()
    if isinstance(account_id, int):
        return account_id
    if isinstance(account_id, str):
        trimmed_id = account_id.strip()
        if trimmed_id.isdigit():
            return int(trimmed_id)
        if trimmed_id:
            raise_tool_error(
                "invalid_request",
                "account_id must be numeric when provided.",
                "Provide account_id as an integer, or use account_number for user-facing account number.",
                status_code=400,
            )

    if isinstance(account_number, int):
        return await client.resolve_id(
            f"/v1/business/{slug}/account/",
            lookup_field="number",
            lookup_value=account_number,
            business_slug=slug,
        )
    if isinstance(account_number, str):
        trimmed_number = account_number.strip()
        if not trimmed_number:
            raise_tool_error(
                "invalid_request",
                "account_number cannot be empty.",
                "Provide account_number as a non-empty numeric value.",
                status_code=400,
            )
        lookup_value: int | str = (
            int(trimmed_number) if trimmed_number.isdigit() else trimmed_number
        )
        return await client.resolve_id(
            f"/v1/business/{slug}/account/",
            lookup_field="number",
            lookup_value=lookup_value,
            business_slug=slug,
        )
    return None
