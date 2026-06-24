"""Invoicing contact MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    ContactCreateInput,
    ContactCreatesInput,
    ContactListItem,
    ContactListInput,
    ContactRetrieveInput,
    ContactSummary,
    ContactUpdateInput,
    ContactUpdatesInput,
    DeletedResponse,
    IdentifiersInput,
    ListEnvelope,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="invoicing_contacts_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description=(
        "List contacts for the selected business. Use this first to ground contact IDs/tool_handles before "
        "update or delete actions. Supports search and filters such as invoicing-enabled, exact name, and "
        "excluded contact ID. For duplicate-review workflows, search by exact name or customer number first "
        "and inspect the returned IDs before deleting anything. Use `contact_business_id` to search by "
        "asiakastunnus."
    ),
    output_schema=ListEnvelope[ContactListItem].model_json_schema(),
)
async def invoicing_contacts_list(
    params: ContactListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    search_value = args.contact_business_id or args.query
    return await get_client().list_page(
        f"/v1/business/{slug}/contacts/",
        params={"search": search_value},
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=ContactListItem,
        handle_resource="invoicing_contact",
        usage_hint=(
            "Use contact_business_id for exact customer number lookup. For duplicate cleanup, list matching "
            "contacts first, review the returned IDs/tool_handles, optionally retrieve the candidates for "
            "verification, and then pass the exact identifiers to invoicing_contact_delete in one batched "
            "call."
        ),
    )


@tool(
    name="invoicing_contact_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description=(
        "Retrieve one contact by tool_handle or contact_id for exact follow-up. Use this to verify candidate "
        "duplicate contacts before deleting or editing them."
    ),
)
async def invoicing_contact_retrieve(
    params: ContactRetrieveInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    contact_id = await get_client().resolve_exact_id(
        tool_handle=args.tool_handle,
        internal_id=args.contact_id,
        expected_resource="invoicing_contact",
        id_field_name="contact_id",
    )
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/contacts/{contact_id}/",
        business_slug=slug,
    )
    return dump_model_from_backend(ContactSummary, result)


@tool(
    name="invoicing_contact_create",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Create one or more contacts for invoicing and bookkeeping workflows in a single call — pass each contact as an entry in contacts.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_contact_create(params: ContactCreatesInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/business/{slug}/contacts/"

    async def _create(spec: ContactCreateInput) -> dict[str, Any]:
        result = await get_client().request(
            "POST", path, json_body=_build_contact_create_body(spec), business_slug=slug
        )
        return dump_model_from_backend(ContactSummary, result)

    return await run_batch(params.contacts, _create, label=lambda spec: spec.name)


@tool(
    name="invoicing_contact_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Update one or more contacts in a single call — pass each update spec (identifier + "
        "fields to change) as an entry in contacts. If the user gives asiakastunnus, retrieve "
        "the contact by contact_business_id first."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_contact_update(
    params: ContactUpdatesInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(spec: ContactUpdateInput) -> dict[str, Any]:
        contact_id = (
            int(spec.identifier)
            if spec.identifier.isdigit()
            else await get_client().resolve_id(
                f"/v1/business/{slug}/contacts/",
                lookup_field="name",
                lookup_value=spec.identifier,
                search_param="search",
                business_slug=slug,
            )
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/contacts/{contact_id}/",
            json_body=_build_contact_patch_body(spec),
            business_slug=slug,
        )
        return dump_model_from_backend(ContactSummary, result)

    return await run_batch(params.contacts, _update, label=lambda spec: spec.identifier)


@tool(
    name="invoicing_contact_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Delete one or more contacts in a single call — pass every target (contact ID or exact name) in "
        "identifiers. Prefer one batched call over repeated single-contact calls because each destructive call "
        "needs its own confirmation. For duplicate cleanup, always ground the targets with invoicing_contacts_list "
        "and/or invoicing_contact_retrieve first, then delete only the exact extra records you verified. Never "
        "call this with an empty identifiers list or guessed placeholders. This can fail per contact when it is "
        "already used by invoices or bookkeeping documents."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_contact_delete(params: IdentifiersInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(identifier: str) -> dict[str, Any]:
        contact_id = (
            int(identifier)
            if identifier.isdigit()
            else await get_client().resolve_id(
                f"/v1/business/{slug}/contacts/",
                lookup_field="name",
                lookup_value=identifier,
                search_param="search",
                business_slug=slug,
            )
        )
        await get_client().request(
            "DELETE", f"/v1/business/{slug}/contacts/{contact_id}/", business_slug=slug
        )
        return dump_model(DeletedResponse(id=contact_id))

    return await run_batch(params.identifiers, _delete)


def _build_contact_patch_body(params: ContactUpdateInput) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for field_name in (
        "name",
        "type",
        "customer_id",
        "contact_business_id",
        "invoicing_email",
        "invoicing_electronic_address",
        "invoicing_einvoice_operator",
        "is_invoicing_enabled",
        "invoicing_street",
        "invoicing_city",
        "invoicing_postal_code",
        "invoicing_country",
        "invoicing_language",
        "email",
        "phone",
        "phone_number",
        "notes",
        "name_aliases",
        "vat_number",
        "y_tunnus",
    ):
        if field_name in params.model_fields_set:
            body[field_name] = getattr(params, field_name)
    return body


def _build_contact_create_body(params: ContactCreateInput) -> dict[str, Any]:
    body = {"name": params.name}
    for field_name in (
        "type",
        "customer_id",
        "contact_business_id",
        "invoicing_email",
        "invoicing_electronic_address",
        "invoicing_einvoice_operator",
        "is_invoicing_enabled",
        "invoicing_street",
        "invoicing_city",
        "invoicing_postal_code",
        "invoicing_country",
        "invoicing_language",
        "email",
        "phone",
        "phone_number",
        "notes",
        "name_aliases",
        "vat_number",
        "y_tunnus",
    ):
        value = getattr(params, field_name)
        if value is not None:
            body[field_name] = value
    return body
