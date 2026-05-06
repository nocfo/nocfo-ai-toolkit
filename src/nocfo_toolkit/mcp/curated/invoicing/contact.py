"""Invoicing contact MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.curated.confirmation import confirm_mutation
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    ContactCreateInput,
    ContactListItem,
    ContactListInput,
    ContactRetrieveInput,
    ContactSummary,
    ContactUpdateInput,
    DeletedResponse,
    IdentifierInput,
    ListEnvelope,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="invoicing_contacts_list",
    description=(
        "List contacts for the selected business. Supports search and filters such as invoicing-enabled, "
        "exact name, and excluded contact ID. Use `contact_business_id` to search by asiakastunnus."
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
        usage_hint="Use contact_business_id for exact customer number lookup, then pass tool_handle to invoicing_contact_retrieve.",
    )


@tool(
    name="invoicing_contact_retrieve",
    description="Retrieve one contact by tool_handle or contact_id for exact follow-up.",
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
    description="Create a contact for invoicing and bookkeeping workflows.",
)
async def invoicing_contact_create(params: ContactCreateInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/business/{slug}/contacts/"
    payload = _build_contact_create_body(params)
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_contact_create",
        target_resource={"type": "contact", "id": str(params.name)},
        parameters=payload,
    )
    result = await get_client().request(
        "POST",
        path,
        json_body=payload,
        business_slug=slug,
    )
    return dump_model_from_backend(ContactSummary, result)


@tool(
    name="invoicing_contact_update",
    description=(
        "Update one contact by contact ID or exact name. If the user gives asiakastunnus, "
        "retrieve the contact by contact_business_id first."
    ),
)
async def invoicing_contact_update(
    params: ContactUpdateInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    contact_id = (
        int(params.identifier)
        if params.identifier.isdigit()
        else await get_client().resolve_id(
            f"/v1/business/{slug}/contacts/",
            lookup_field="name",
            lookup_value=params.identifier,
            search_param="search",
            business_slug=slug,
        )
    )
    path = f"/v1/business/{slug}/contacts/{contact_id}/"
    payload = _build_contact_patch_body(params)
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_contact_update",
        target_resource={"type": "contact", "id": contact_id},
        parameters=payload,
    )
    result = await get_client().request(
        "PATCH",
        path,
        json_body=payload,
        business_slug=slug,
    )
    return dump_model_from_backend(ContactSummary, result)


@tool(
    name="invoicing_contact_delete",
    description=(
        "Delete one contact by contact ID or exact name. This can fail when the contact is already used "
        "by invoices or bookkeeping documents."
    ),
)
async def invoicing_contact_delete(params: IdentifierInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    contact_id = (
        int(args.identifier)
        if args.identifier.isdigit()
        else await get_client().resolve_id(
            f"/v1/business/{slug}/contacts/",
            lookup_field="name",
            lookup_value=args.identifier,
            search_param="search",
            business_slug=slug,
        )
    )
    path = f"/v1/business/{slug}/contacts/{contact_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_contact_delete",
        target_resource={"type": "contact", "id": contact_id},
    )
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(id=contact_id))


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
        "invoicing_country",
        "invoicing_language",
        "email",
        "phone",
        "vat_number",
        "y_tunnus",
        "city",
        "country",
        "address",
        "zip_code",
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
        "invoicing_country",
        "invoicing_language",
        "email",
        "phone",
        "vat_number",
        "y_tunnus",
        "city",
        "country",
        "address",
        "zip_code",
    ):
        value = getattr(params, field_name)
        if value is not None:
            body[field_name] = value
    return body
