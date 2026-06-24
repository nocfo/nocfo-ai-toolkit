"""Purchase invoice MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    DeletedResponse,
    InvoiceNumbersInput,
    InvoiceNumbersPayloadInput,
    InvoiceRetrieveInput,
    ListEnvelope,
    PurchaseInvoiceListItem,
    PurchaseInvoicesListInput,
    PurchaseInvoiceSummary,
    dump_model,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle


@tool(
    name="invoicing_purchase_invoices_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description=(
        "List purchase invoices for the selected business. Use this first to ground exact invoice numbers/tool_handles "
        "before updating or deleting invoices. Use `invoice_number` for deterministic lookup. `import_source`, "
        "`is_paid`, and `is_past_due` narrow compact scans before falling back to `search`."
    ),
    output_schema=ListEnvelope[PurchaseInvoiceListItem].model_json_schema(),
)
async def invoicing_purchase_invoices_list(
    params: PurchaseInvoicesListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/invoicing/{slug}/purchase_invoice/",
        params=args.query_params(),
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=PurchaseInvoiceListItem,
        handle_resource="invoicing_purchase_invoice",
        usage_hint=(
            "Use invoice_number/date/state filters for browsing. Then use tool_handle with "
            "invoicing_purchase_invoice_retrieve for full invoice data. Before update/delete actions, ground the "
            "exact targets here first and then batch the confirmed invoice numbers into one mutation call."
        ),
    )


@tool(
    name="invoicing_purchase_invoice_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description=(
        "Retrieve one purchase invoice from invoicing_purchase_invoices_list.items[].tool_handle. When linked to imported banking data, "
        "related bank transaction and document details are included for exact follow-up."
    ),
)
async def invoicing_purchase_invoice_retrieve(
    params: InvoiceRetrieveInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    purchase_invoice_id = decode_tool_handle(
        args.tool_handle,
        expected_resource="invoicing_purchase_invoice",
    )
    result = await get_client().request(
        "GET",
        f"/v1/invoicing/{slug}/purchase_invoice/{purchase_invoice_id}/",
        business_slug=slug,
    )
    return dump_model_from_backend(PurchaseInvoiceSummary, result)


@tool(
    name="invoicing_purchase_invoice_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Update one or more purchase invoices selected by invoice_numbers; the same payload is applied to every "
        "invoice. Ground the exact invoice numbers first, then batch all confirmed targets into one call."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_purchase_invoice_update(
    params: InvoiceNumbersPayloadInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(invoice_number: int | str) -> dict[str, Any]:
        purchase_invoice_id = await get_client().resolve_id(
            f"/v1/invoicing/{slug}/purchase_invoice/",
            lookup_field="invoice_number",
            lookup_value=invoice_number,
            search_param="search",
            business_slug=slug,
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/invoicing/{slug}/purchase_invoice/{purchase_invoice_id}/",
            json_body=params.payload,
            business_slug=slug,
        )
        return dump_model_from_backend(PurchaseInvoiceSummary, result)

    return await run_batch(params.invoice_numbers, _update)


@tool(
    name="invoicing_purchase_invoice_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Delete one or more purchase invoices in a single call — pass every target in invoice_numbers. Ground the "
        "exact invoice numbers first with invoicing_purchase_invoices_list and/or invoicing_purchase_invoice_retrieve, "
        "then batch all confirmed targets into one call. Never call this with guessed placeholders or an empty "
        "target set. Prefer one batched call over repeated single-target calls (each call needs its own confirmation)."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_purchase_invoice_delete(
    params: InvoiceNumbersInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(invoice_number: int | str) -> dict[str, Any]:
        purchase_invoice_id = await get_client().resolve_id(
            f"/v1/invoicing/{slug}/purchase_invoice/",
            lookup_field="invoice_number",
            lookup_value=invoice_number,
            search_param="search",
            business_slug=slug,
        )
        await get_client().request(
            "DELETE",
            f"/v1/invoicing/{slug}/purchase_invoice/{purchase_invoice_id}/",
            business_slug=slug,
        )
        return dump_model(DeletedResponse(invoice_number=invoice_number))

    return await run_batch(params.invoice_numbers, _delete)
