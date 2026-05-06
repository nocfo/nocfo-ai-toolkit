"""Invoicing product MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BusinessPaginationInput,
    DeletedResponse,
    IdentifierInput,
    IdentifierPayloadInput,
    ListEnvelope,
    PayloadInput,
    ProductListItem,
    ProductSummary,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="invoicing_products_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description=(
        "List invoicing products for the selected business. Products are reusable invoice row templates "
        "and support code/name search. Use `code` for deterministic lookup when the product code is known."
    ),
    output_schema=ListEnvelope[ProductListItem].model_json_schema(),
)
async def invoicing_products_list(
    params: BusinessPaginationInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/invoicing/{slug}/product/",
        params={"search": args.query},
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=ProductListItem,
        handle_resource="invoicing_product",
        usage_hint="Use product code/name query in list, then use tool_handle with invoicing_product_retrieve for full details.",
    )


@tool(
    name="invoicing_product_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description=(
        "Retrieve one product by ID. If ID is unknown, call `invoicing_products_list` "
        "with `code` first, then use `search` as fallback."
    ),
)
async def invoicing_product_retrieve(params: IdentifierInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    if args.identifier.isdigit():
        result = await get_client().request(
            "GET",
            f"/v1/invoicing/{slug}/product/{int(args.identifier)}/",
            business_slug=slug,
        )
        return dump_model_from_backend(ProductSummary, result)
    return await get_client().retrieve_by_lookup(
        f"/v1/invoicing/{slug}/product/",
        f"/v1/invoicing/{slug}/product/{{id}}/",
        lookup_field="code",
        lookup_value=args.identifier,
        params={"search": args.identifier},
        business_slug=slug,
        item_model=ProductSummary,
    )


@tool(
    name="invoicing_product_create",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Create an invoicing product. Set is_vat_inclusive explicitly because it controls whether amount is VAT-inclusive or VAT-exclusive.",
)
async def invoicing_product_create(params: PayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/invoicing/{slug}/product/"
    result = await get_client().request(
        "POST",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(ProductSummary, result)


@tool(
    name="invoicing_product_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Update one invoicing product. Keep amount and is_vat_inclusive aligned (true=VAT-inclusive amount, false=VAT-exclusive amount). Prefer resolving by product code first.",
)
async def invoicing_product_update(
    params: IdentifierPayloadInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    product_id = (
        int(args.identifier)
        if args.identifier.isdigit()
        else await get_client().resolve_id(
            f"/v1/invoicing/{slug}/product/",
            lookup_field="code",
            lookup_value=args.identifier,
            search_param="search",
            business_slug=slug,
        )
    )
    path = f"/v1/invoicing/{slug}/product/{product_id}/"
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(ProductSummary, result)


@tool(
    name="invoicing_product_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one invoicing product. Prefer resolving it by product code first.",
)
async def invoicing_product_delete(params: IdentifierInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    product_id = (
        int(args.identifier)
        if args.identifier.isdigit()
        else await get_client().resolve_id(
            f"/v1/invoicing/{slug}/product/",
            lookup_field="code",
            lookup_value=args.identifier,
            search_param="search",
            business_slug=slug,
        )
    )
    path = f"/v1/invoicing/{slug}/product/{product_id}/"
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(id=product_id))
