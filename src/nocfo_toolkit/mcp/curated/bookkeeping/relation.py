"""Bookkeeping document relation MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.tool_access import ToolTag
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.bookkeeping.document import document_by_number
from nocfo_toolkit.mcp.curated.schemas import (
    DeletedResponse,
    DocumentRelationCreateInput,
    DocumentRelationIdInput,
    EntryListInput,
    ListEnvelope,
    RelationSummary,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="bookkeeping_document_relations_list",
    tags={ToolTag.READ_ONLY.value},
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
    tags={ToolTag.READ_ONLY.value},
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
    description="Create a relation between two documents using document numbers and relation role/type.",
)
async def bookkeeping_document_relation_create(
    params: DocumentRelationCreateInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    related = await document_by_number(slug, args.related_document_number)
    path = f"/v1/business/{slug}/document/{document['id']}/relation/"
    payload = {
        "related_document": related["id"],
        "role": args.role.value,
        "type": args.type.value,
    }
    result = await get_client().request(
        "POST",
        path,
        json_body=payload,
        business_slug=slug,
    )
    return dump_model_from_backend(RelationSummary, result)


@tool(
    name="bookkeeping_document_relation_delete",
    description="Delete a relation listed for the same document context.",
)
async def bookkeeping_document_relation_delete(
    params: DocumentRelationIdInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    path = f"/v1/business/{slug}/document/{document['id']}/relation/{args.relation_id}/"
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(relation_id=args.relation_id))
