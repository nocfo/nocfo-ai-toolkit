"""Purchase invoice MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.tool_access import ToolTag
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    DeletedResponse,
    InvoiceLookupInput,
    InvoiceRetrieveInput,
    InvoicePayloadInput,
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
    tags={ToolTag.READ_ONLY.value},
    description=(
        "List purchase invoices for the selected business. Use `invoice_number` for deterministic lookup. "
        "`import_source`, `is_paid`, and `is_past_due` narrow compact scans before falling back to `search`."
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
        usage_hint="Use invoice_number/date/state filters for browsing. Then use tool_handle with invoicing_purchase_invoice_retrieve for full invoice data.",
    )


@tool(
    name="invoicing_purchase_invoice_retrieve",
    tags={ToolTag.READ_ONLY.value},
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
    description=("Update one purchase invoice by user-facing invoice_number."),
)
async def invoicing_purchase_invoice_update(
    params: InvoicePayloadInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    purchase_invoice_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/purchase_invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        search_param="search",
        business_slug=slug,
    )
    path = f"/v1/invoicing/{slug}/purchase_invoice/{purchase_invoice_id}/"
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(PurchaseInvoiceSummary, result)


@tool(
    name="invoicing_purchase_invoice_delete",
    description=("Delete one purchase invoice by user-facing invoice_number."),
)
async def invoicing_purchase_invoice_delete(
    params: InvoiceLookupInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    purchase_invoice_id = await get_client().resolve_id(
        f"/v1/invoicing/{slug}/purchase_invoice/",
        lookup_field="invoice_number",
        lookup_value=args.invoice_number,
        search_param="search",
        business_slug=slug,
    )
    path = f"/v1/invoicing/{slug}/purchase_invoice/{purchase_invoice_id}/"
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(invoice_number=args.invoice_number))
