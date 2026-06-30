"""Sales invoice MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    DeletedResponse,
    InvoiceRetrieveInput,
    InvoiceUpdateItem,
    InvoiceUpdatesInput,
    ListEnvelope,
    PayloadsInput,
    SalesInvoiceAction,
    SalesInvoiceActionItem,
    SalesInvoiceActionsInput,
    SalesInvoiceListItem,
    SalesInvoiceLookupInput,
    SalesInvoiceMutationPayload,
    SalesInvoiceSendItem,
    SalesInvoiceSendsInput,
    SalesInvoiceTargetsInput,
    SalesInvoicesListInput,
    SalesInvoiceSummary,
    dump_model,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle


@tool(
    name="invoicing_sales_invoices_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List sales invoices by invoice number, status, dates, receiver, reference, or query. Use this first to ground exact invoice numbers/tool_handles before update, delete, send, or workflow actions.",
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
        usage_hint=(
            "Use invoice_number/status/date filters for browsing. Then use tool_handle with "
            "invoicing_sales_invoice_retrieve for full invoice data. Before update/delete/send/action requests, "
            "ground the exact targets here first and then batch the confirmed invoice numbers or tool_handles into "
            "one mutation call."
        ),
    )


@tool(
    name="invoicing_sales_invoice_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve one sales invoice from invoicing_sales_invoices_list.items[].tool_handle. Use this to verify an invoice before deleting it, sending it, or applying a workflow action.",
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
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Create one or more sales invoices in a single call — pass each invoice (fields and rows) as an entry in payloads.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_sales_invoice_create(params: PayloadsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/invoicing/{slug}/invoice/"

    async def _create(payload: dict[str, Any]) -> dict[str, Any]:
        body = await resolve_sales_invoice_payload(slug, payload)
        result = await get_client().request(
            "POST", path, json_body=body, business_slug=slug
        )
        return dump_model_from_backend(SalesInvoiceSummary, result)

    return await run_batch(params.payloads, _create, label=lambda _payload: None)


@tool(
    name="invoicing_sales_invoice_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Update one or more sales invoices in a single confirmed call — pass each update (invoice_number or tool_handle, plus the fields to change for THAT invoice) as an entry in updates. Different invoices can get different changes in one call. To change when an invoice is due, set payment_condition_days (the payment term in days) — due_date is derived from the invoicing date plus that term and cannot be set directly. Ground the exact targets first.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_sales_invoice_update(
    params: InvoiceUpdatesInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(item: InvoiceUpdateItem) -> dict[str, Any]:
        body = await resolve_sales_invoice_payload(slug, item.payload)
        item_id = await _resolve_invoice_item(slug, item)
        result = await get_client().request(
            "PATCH",
            f"/v1/invoicing/{slug}/invoice/{item_id}/",
            json_body=body,
            business_slug=slug,
        )
        return dump_model_from_backend(SalesInvoiceSummary, result)

    return await run_batch(
        params.updates,
        _update,
        label=lambda item: (
            item.invoice_number if item.invoice_number is not None else item.tool_handle
        ),
    )


@tool(
    name="invoicing_sales_invoice_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more sales invoices in a single call — pass every target in invoice_numbers or tool_handles. Ground the exact targets first with invoicing_sales_invoices_list and/or invoicing_sales_invoice_retrieve, then batch all confirmed invoices into one call. Never call this with guessed placeholders or an empty target set. Prefer one batched call over repeated single-target calls (each call needs its own confirmation).",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_sales_invoice_delete(
    params: SalesInvoiceTargetsInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    targets, kind = _sales_invoice_targets(params)

    async def _delete(target: int | str) -> dict[str, Any]:
        item_id = await _resolve_target(slug, target, kind)
        await get_client().request(
            "DELETE", f"/v1/invoicing/{slug}/invoice/{item_id}/", business_slug=slug
        )
        invoice_number = target if kind == "invoice_number" else None
        return dump_model(DeletedResponse(invoice_number=invoice_number, id=item_id))

    return await run_batch(targets, _delete)


@tool(
    name="invoicing_sales_invoice_action",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Run a workflow action (accept, mark_paid, mark_unpaid, mark_credit_loss, or disable_recurrence) on one or more sales invoices in a single confirmed call — pass each action (invoice_number or tool_handle, plus the action for THAT invoice) as an entry in actions. Different invoices can get different actions (e.g. mark one paid and another credit_loss) in one call. First obtain the exact targets from invoicing_sales_invoices_list or invoicing_sales_invoice_retrieve.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_sales_invoice_action(
    params: SalesInvoiceActionsInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path_by_action = {
        SalesInvoiceAction.accept: "accept",
        SalesInvoiceAction.mark_paid: "paid",
        SalesInvoiceAction.mark_unpaid: "unpaid",
        SalesInvoiceAction.mark_credit_loss: "credit_loss",
        SalesInvoiceAction.disable_recurrence: "disable_recurrence",
    }

    async def _act(item: SalesInvoiceActionItem) -> dict[str, Any]:
        action_mapped = path_by_action.get(item.action)
        if action_mapped is None:
            raise_tool_error(
                "invalid_request",
                f"Unsupported sales invoice action: {item.action}.",
                "Use accept, mark_paid, mark_unpaid, mark_credit_loss, or disable_recurrence.",
                status_code=400,
            )
        item_id = await _resolve_invoice_item(slug, item)
        result = await get_client().request(
            "POST",
            f"/v1/invoicing/{slug}/invoice/{item_id}/actions/{action_mapped}/",
            business_slug=slug,
        )
        return dump_model_from_backend(SalesInvoiceSummary, result)

    return await run_batch(
        params.actions,
        _act,
        label=lambda item: (
            item.invoice_number if item.invoice_number is not None else item.tool_handle
        ),
    )


@tool(
    name="invoicing_sales_invoice_delivery_methods",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List available delivery methods before sending a sales invoice.",
)
async def invoicing_sales_invoice_delivery_methods(
    params: SalesInvoiceLookupInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    item_id = await _resolve_sales_invoice_id(slug, args)
    result = await get_client().request(
        "GET",
        f"/v1/invoicing/{slug}/invoice/{item_id}/delivery_methods/",
        business_slug=slug,
    )
    return {"items": result if isinstance(result, list) else []}


@tool(
    name="invoicing_sales_invoice_send",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=True,
    ),
    description="Send one or more sales invoices in a single confirmed call — pass each send (invoice_number or tool_handle, a delivery_method, and for EMAIL an email_subject + optional email_content) as an entry in sends. Different invoices can use different delivery methods in one call. Each invoice must be in ACCEPTED state first. Ground the exact targets with invoicing_sales_invoices_list or invoicing_sales_invoice_retrieve, and check invoicing_sales_invoice_delivery_methods when needed. Call only after the user explicitly confirms sending.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_sales_invoice_send(
    params: SalesInvoiceSendsInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _send(item: SalesInvoiceSendItem) -> dict[str, Any]:
        item_id = await _resolve_invoice_item(slug, item)
        result = await get_client().request(
            "POST",
            f"/v1/invoicing/{slug}/invoice/{item_id}/send/",
            json_body=_build_send_body(item),
            business_slug=slug,
        )
        return dump_model_from_backend(SalesInvoiceSummary, result)

    return await run_batch(
        params.sends,
        _send,
        label=lambda item: (
            item.invoice_number if item.invoice_number is not None else item.tool_handle
        ),
    )


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

    if isinstance(payload_data, dict) and "due_date" in payload_data:
        raise_tool_error(
            "invalid_request",
            "due_date is read-only; it is calculated from the invoicing date and the payment term.",
            "To change when an invoice is due, set payment_condition_days (the payment term in days): "
            "due_date = invoicing_date + payment_condition_days.",
            status_code=400,
        )

    body = SalesInvoiceMutationPayload.model_validate(payload_data).model_dump(
        mode="json",
        by_alias=True,
        exclude_unset=True,
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


async def _resolve_sales_invoice_id(slug: str, args: SalesInvoiceLookupInput) -> int:
    if args.tool_handle:
        return decode_tool_handle(
            args.tool_handle,
            expected_resource="invoicing_sales_invoice",
        )
    assert args.invoice_number is not None
    return await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        business_slug=slug,
    )


def _sales_invoice_targets(
    params: SalesInvoiceTargetsInput,
) -> tuple[list[Any], str]:
    """Return (targets, kind) for the selector list the caller provided."""
    if params.tool_handles:
        return list(params.tool_handles), "tool_handle"
    return list(params.invoice_numbers or []), "invoice_number"


async def _resolve_target(slug: str, target: Any, kind: str) -> int:
    if kind == "tool_handle":
        return decode_tool_handle(target, expected_resource="invoicing_sales_invoice")
    return await get_client().resolve_id(
        f"/v1/invoicing/{slug}/invoice/",
        lookup_field="invoice_number",
        lookup_value=target,
        business_slug=slug,
    )


async def _resolve_invoice_item(slug: str, item: Any) -> int:
    """Resolve a single invoice id from an item carrying invoice_number XOR tool_handle."""
    if item.tool_handle is not None:
        return await _resolve_target(slug, item.tool_handle, "tool_handle")
    return await _resolve_target(slug, item.invoice_number, "invoice_number")


def _build_send_body(item: Any) -> dict[str, Any]:
    """Backend send shape: {delivery_method, data:{email_subject, email_content}}.

    The backend `data` serializer requires both keys for email delivery (content is
    nullable), so include email_content explicitly (null when not provided).
    """
    method = getattr(item.delivery_method, "value", item.delivery_method)
    body: dict[str, Any] = {"delivery_method": method}
    if item.email_subject is not None or item.email_content is not None:
        body["data"] = {
            "email_subject": item.email_subject,
            "email_content": item.email_content,
        }
    return body
