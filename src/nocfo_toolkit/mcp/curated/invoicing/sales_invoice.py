"""Sales invoice MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.curated.confirmation import confirm_mutation
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    DeletedResponse,
    InvoiceLookupInput,
    InvoiceRetrieveInput,
    InvoicePayloadInput,
    ListEnvelope,
    SalesInvoiceAction,
    SalesInvoiceActionInput,
    SalesInvoiceListItem,
    SalesInvoiceMutationPayload,
    SalesInvoicesListInput,
    SalesInvoiceSummary,
    PayloadInput,
    dump_model,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle


@tool(
    name="invoicing_sales_invoices_list",
    description="List sales invoices by invoice number, status, dates, receiver, reference, or query.",
    output_schema=ListEnvelope[SalesInvoiceListItem].model_json_schema(),
)
async def invoicing_sales_invoices_list(
    params: SalesInvoicesListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/invoicing/{slug}/invoice/",
        params=args.query_params(),
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=SalesInvoiceListItem,
        handle_resource="invoicing_sales_invoice",
        usage_hint="Use invoice_number/status/date filters for browsing. Then use tool_handle with invoicing_sales_invoice_retrieve for full invoice data.",
    )


@tool(
    name="invoicing_sales_invoice_retrieve",
    description="Retrieve one sales invoice from invoicing_sales_invoices_list.items[].tool_handle.",
)
async def invoicing_sales_invoice_retrieve(
    params: InvoiceRetrieveInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    item_id = decode_tool_handle(
        args.tool_handle,
        expected_resource="invoicing_sales_invoice",
    )
    result = await get_client().request(
        "GET", f"/v1/invoicing/{slug}/invoice/{item_id}/", business_slug=slug
    )
    return dump_model_from_backend(SalesInvoiceSummary, result)


@tool(
    name="invoicing_sales_invoice_create",
    description="Create a sales invoice using invoice fields and rows from the user request.",
)
async def invoicing_sales_invoice_create(params: PayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    body = await resolve_sales_invoice_payload(slug, args.payload)
    path = f"/v1/invoicing/{slug}/invoice/"
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_sales_invoice_create",
        target_resource={
            "type": "sales_invoice",
            "id": str(body.get("invoice_number") or "new"),
        },
        parameters=body,
    )
    result = await get_client().request(
        "POST",
        path,
        json_body=body,
        business_slug=slug,
    )
    return dump_model_from_backend(SalesInvoiceSummary, result)


@tool(
    name="invoicing_sales_invoice_update",
    description="Update a sales invoice by user-facing invoice_number.",
)
async def invoicing_sales_invoice_update(
    params: InvoicePayloadInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    body = await resolve_sales_invoice_payload(slug, args.payload)
    item_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        business_slug=slug,
    )
    path = f"/v1/invoicing/{slug}/invoice/{item_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_sales_invoice_update",
        target_resource={
            "type": "sales_invoice",
            "id": item_id,
        },
        parameters=body,
    )
    result = await get_client().request(
        "PATCH",
        path,
        json_body=body,
        business_slug=slug,
    )
    return dump_model_from_backend(SalesInvoiceSummary, result)


@tool(
    name="invoicing_sales_invoice_delete",
    description="Delete a sales invoice by user-facing invoice_number.",
)
async def invoicing_sales_invoice_delete(
    params: InvoiceLookupInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    item_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        business_slug=slug,
    )
    path = f"/v1/invoicing/{slug}/invoice/{item_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_sales_invoice_delete",
        target_resource={
            "type": "sales_invoice",
            "id": item_id,
        },
    )
    await get_client().request("DELETE", path, business_slug=slug)
    return dump_model(DeletedResponse(invoice_number=args.invoice_number))


@tool(
    name="invoicing_sales_invoice_action",
    description="Run a sales invoice workflow action: accept, mark_paid, mark_unpaid, mark_credit_loss, or disable_recurrence.",
)
async def invoicing_sales_invoice_action(
    params: SalesInvoiceActionInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    item_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        business_slug=slug,
    )
    path_by_action = {
        SalesInvoiceAction.accept: "accept",
        SalesInvoiceAction.mark_paid: "paid",
        SalesInvoiceAction.mark_unpaid: "unpaid",
        SalesInvoiceAction.mark_credit_loss: "credit_loss",
        SalesInvoiceAction.disable_recurrence: "disable_recurrence",
    }
    path = (
        f"/v1/invoicing/{slug}/invoice/{item_id}/actions/{path_by_action[args.action]}/"
    )
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_sales_invoice_action",
        target_resource={
            "type": "sales_invoice",
            "id": item_id,
        },
    )
    result = await get_client().request(
        "POST",
        path,
        business_slug=slug,
    )
    return dump_model_from_backend(SalesInvoiceSummary, result)


@tool(
    name="invoicing_sales_invoice_delivery_methods",
    description="List available delivery methods before sending a sales invoice.",
)
async def invoicing_sales_invoice_delivery_methods(
    params: InvoiceLookupInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    item_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        business_slug=slug,
    )
    result = await get_client().request(
        "GET",
        f"/v1/invoicing/{slug}/invoice/{item_id}/delivery_methods/",
        business_slug=slug,
    )
    return {"items": result if isinstance(result, list) else []}


@tool(
    name="invoicing_sales_invoice_send",
    description="Send a sales invoice using a selected delivery method. Call only after the user explicitly confirms sending.",
)
async def invoicing_sales_invoice_send(
    params: InvoicePayloadInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    item_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        business_slug=slug,
    )
    path = f"/v1/invoicing/{slug}/invoice/{item_id}/send/"
    await confirm_mutation(
        business=slug,
        tool_name="invoicing_sales_invoice_send",
        target_resource={
            "type": "sales_invoice",
            "id": item_id,
        },
        parameters=args.payload,
    )
    result = await get_client().request(
        "POST",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(SalesInvoiceSummary, result)


async def resolve_sales_invoice_payload(
    slug_or_ctx: Any, payload_or_slug: Any, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    # Backward compatible helper signature:
    # - new: resolve_sales_invoice_payload(slug, payload)
    # - old: resolve_sales_invoice_payload(ctx, slug, payload)
    if payload is None:
        slug = str(slug_or_ctx)
        payload_data = payload_or_slug
        client = get_client()
    else:
        slug = str(payload_or_slug)
        payload_data = payload
        client = getattr(slug_or_ctx, "client", None) or get_client()

    body = SalesInvoiceMutationPayload.model_validate(payload_data).model_dump(
        mode="json",
        by_alias=True,
    )
    await _resolve_receiver_reference(client, slug, body)
    return body


async def _resolve_receiver_reference(
    client: Any, slug: str, body: dict[str, Any]
) -> None:
    if "receiver" not in body:
        return

    receiver_value = body["receiver"]

    if isinstance(receiver_value, int):
        body["receiver"] = receiver_value
        return

    if isinstance(receiver_value, str):
        trimmed = receiver_value.strip()
        if not trimmed:
            raise_tool_error(
                "invalid_request",
                "receiver cannot be empty.",
                "Provide receiver as contact ID, contact tool_handle, or exact contact name.",
                status_code=400,
            )
        if trimmed.isdigit():
            body["receiver"] = int(trimmed)
            return
        try:
            body["receiver"] = decode_tool_handle(
                trimmed,
                expected_resource="invoicing_contact",
            )
            return
        except Exception:
            body["receiver"] = await client.resolve_id(
                f"/v1/business/{slug}/contacts/",
                lookup_field="name",
                lookup_value=trimmed,
                search_param="search",
                business_slug=slug,
            )
            return

    raise_tool_error(
        "invalid_request",
        "receiver must be a contact reference.",
        "Provide receiver as contact ID, contact tool_handle, exact contact name, or {id: <contact_id>}.",
        status_code=400,
    )
