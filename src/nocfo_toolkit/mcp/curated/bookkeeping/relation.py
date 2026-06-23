"""Bookkeeping document relation MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.bookkeeping.document import document_by_number
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    DeletedResponse,
    DocumentRelationCreatesInput,
    DocumentRelationCreateSpec,
    DocumentRelationDeletesInput,
    EntryListInput,
    ListEnvelope,
    RelationSummary,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="bookkeeping_document_relations_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List document-to-document relations for a context document.",
    output_schema=ListEnvelope[RelationSummary].model_json_schema(),
)
async def bookkeeping_document_relations_list(
    params: EntryListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    return await get_client().list_page(
        f"/v1/business/{slug}/document/{document['id']}/relation/",
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=RelationSummary,
    )


@tool(
    name="bookkeeping_document_relation_suggestions_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List suggested document relations with reasons and scores.",
    output_schema=ListEnvelope[RelationSummary].model_json_schema(),
)
async def bookkeeping_document_relation_suggestions_list(
    params: EntryListInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    return await get_client().list_page(
        f"/v1/business/{slug}/document/{document['id']}/relation/suggestions/",
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=RelationSummary,
    )


@tool(
    name="bookkeeping_document_relation_create",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Create one or more relations between documents in a single call — pass each relation (document numbers + role/type) as an entry in relations.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_document_relation_create(
    params: DocumentRelationCreatesInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _create(spec: DocumentRelationCreateSpec) -> dict[str, Any]:
        document = await document_by_number(slug, spec.document_number)
        related = await document_by_number(slug, spec.related_document_number)
        path = f"/v1/business/{slug}/document/{document['id']}/relation/"
        payload = {
            "related_document": related["id"],
            "role": spec.role.value,
            "type": spec.type.value,
        }
        result = await get_client().request(
            "POST", path, json_body=payload, business_slug=slug
        )
        return dump_model_from_backend(RelationSummary, result)

    return await run_batch(
        params.relations, _create, label=lambda spec: spec.document_number
    )


@tool(
    name="bookkeeping_document_relation_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more relations for the same document context in a single call — pass every target in relation_ids.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_document_relation_delete(
    params: DocumentRelationDeletesInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    document = await document_by_number(slug, params.document_number)

    async def _delete(relation_id: int) -> dict[str, Any]:
        path = f"/v1/business/{slug}/document/{document['id']}/relation/{relation_id}/"
        await get_client().request("DELETE", path, business_slug=slug)
        return dump_model(DeletedResponse(relation_id=relation_id))

    return await run_batch(params.relation_ids, _delete)
