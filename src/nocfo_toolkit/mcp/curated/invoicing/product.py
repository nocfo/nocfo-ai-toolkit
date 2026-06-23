"""Invoicing product MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    BusinessPaginationInput,
    DeletedResponse,
    IdentifierInput,
    IdentifiersInput,
    IdentifiersPayloadInput,
    ListEnvelope,
    PayloadsInput,
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
    description="Create one or more invoicing products in a single call — pass each product as an entry in payloads. Set is_vat_inclusive explicitly because it controls whether amount is VAT-inclusive or VAT-exclusive.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_product_create(params: PayloadsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/invoicing/{slug}/product/"

    async def _create(payload: dict[str, Any]) -> dict[str, Any]:
        result = await get_client().request(
            "POST", path, json_body=payload, business_slug=slug
        )
        return dump_model_from_backend(ProductSummary, result)

    return await run_batch(
        params.payloads,
        _create,
        label=lambda payload: payload.get("code") or payload.get("name"),
    )


@tool(
    name="invoicing_product_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Update one or more invoicing products selected by identifiers; the same payload is applied to every product. Keep amount and is_vat_inclusive aligned (true=VAT-inclusive amount, false=VAT-exclusive amount). Prefer resolving by product code.",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_product_update(
    params: IdentifiersPayloadInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(identifier: str) -> dict[str, Any]:
        product_id = (
            int(identifier)
            if identifier.isdigit()
            else await get_client().resolve_id(
                f"/v1/invoicing/{slug}/product/",
                lookup_field="code",
                lookup_value=identifier,
                search_param="search",
                business_slug=slug,
            )
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/invoicing/{slug}/product/{product_id}/",
            json_body=params.payload,
            business_slug=slug,
        )
        return dump_model_from_backend(ProductSummary, result)

    return await run_batch(params.identifiers, _update)


@tool(
    name="invoicing_product_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more invoicing products in a single call — pass every target in identifiers. Prefer resolving by product code. Prefer one batched call over repeated single-target calls (each call needs its own confirmation).",
    output_schema=BatchResponse.model_json_schema(),
)
async def invoicing_product_delete(params: IdentifiersInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(identifier: str) -> dict[str, Any]:
        product_id = (
            int(identifier)
            if identifier.isdigit()
            else await get_client().resolve_id(
                f"/v1/invoicing/{slug}/product/",
                lookup_field="code",
                lookup_value=identifier,
                search_param="search",
                business_slug=slug,
            )
        )
        await get_client().request(
            "DELETE", f"/v1/invoicing/{slug}/product/{product_id}/", business_slug=slug
        )
        return dump_model(DeletedResponse(id=product_id))

    return await run_batch(params.identifiers, _delete)
