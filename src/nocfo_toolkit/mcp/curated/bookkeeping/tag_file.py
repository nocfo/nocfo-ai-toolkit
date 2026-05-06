"""Bookkeeping tag and file MCP tools."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from nocfo_toolkit.mcp.tool_access import ToolTag
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.bookkeeping.document import document_by_number
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    DeletedResponse,
    DocumentSummary,
    FileSummary,
    FileUploadInput,
    IdInput,
    IdPayloadInput,
    TagSummary,
    TagListInput,
    TagNamesInput,
    PayloadInput,
    ListEnvelope,
    dump_model,
    dump_model_from_backend,
)


@tool(
    name="bookkeeping_tags_list",
    tags={ToolTag.READ_ONLY.value},
    description="List business tags used across bookkeeping documents and invoices, and as tag filters in reporting.",
    output_schema=ListEnvelope[TagSummary].model_json_schema(),
)
async def bookkeeping_tags_list(params: TagListInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/business/{slug}/tags/",
        params={"search": args.query},
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=TagSummary,
    )


@tool(
    name="bookkeeping_tag_create",
    description="Create a new business tag. Tags can be reused across documents and invoices, and for report filtering. Use this first when the requested tag name does not yet exist, then apply it to documents with bookkeeping_document_tags_update.",
)
async def bookkeeping_tag_create(params: PayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    tag_name = str(args.payload.get("name") or "").strip()
    path = f"/v1/business/{slug}/tags/"
    try:
        result = await get_client().request(
            "POST",
            path,
            json_body=args.payload,
            business_slug=slug,
        )
    except ToolError as exc:
        if not tag_name or not _is_duplicate_tag_name_error(exc):
            raise
        existing_tag_id = await get_client().resolve_id(
            f"/v1/business/{slug}/tags/",
            lookup_field="name",
            lookup_value=tag_name,
            search_param="search",
            business_slug=slug,
        )
        result = await get_client().request(
            "GET",
            f"/v1/business/{slug}/tags/{existing_tag_id}/",
            business_slug=slug,
        )
    return dump_model_from_backend(TagSummary, result)


@tool(
    name="bookkeeping_tag_retrieve",
    tags={ToolTag.READ_ONLY.value},
    description="Retrieve one business tag by tag_id from bookkeeping_tags_list.",
)
async def bookkeeping_tag_retrieve(params: IdInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    result = await get_client().request(
        "GET", f"/v1/business/{slug}/tags/{args.id}/", business_slug=slug
    )
    return dump_model_from_backend(TagSummary, result)


@tool(
    name="bookkeeping_tag_update",
    description="Update one business tag by tag_id from bookkeeping_tags_list.",
)
async def bookkeeping_tag_update(params: IdPayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/business/{slug}/tags/{args.id}/"
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(TagSummary, result)


@tool(
    name="bookkeeping_tag_delete",
    description="Delete one business tag by tag_id from bookkeeping_tags_list.",
)
async def bookkeeping_tag_delete(params: IdInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/business/{slug}/tags/{args.id}/"
    await get_client().request("DELETE", path, business_slug=slug)
    return dump_model(DeletedResponse(tag_id=args.id))


@tool(
    name="bookkeeping_document_tags_update",
    description="Replace a document's tags by document_number and tag names. Use shared business tags from bookkeeping_tags_list. Tag names must already exist; create missing tags first with bookkeeping_tag_create.",
)
async def bookkeeping_document_tags_update(params: TagNamesInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    document = await document_by_number(slug, args.document_number)
    tag_ids = [
        await get_client().resolve_id(
            f"/v1/business/{slug}/tags/",
            lookup_field="name",
            lookup_value=name,
            search_param="search",
            business_slug=slug,
        )
        for name in args.tag_names
    ]
    path = f"/v1/business/{slug}/document/{document['id']}/"
    result = await get_client().request(
        "PATCH",
        path,
        json_body={"tag_ids": tag_ids},
        business_slug=slug,
    )
    return dump_model_from_backend(DocumentSummary, result)


@tool(
    name="bookkeeping_files_list",
    tags={ToolTag.READ_ONLY.value},
    description="List uploaded files/attachments metadata.",
    output_schema=ListEnvelope[FileSummary].model_json_schema(),
)
async def bookkeeping_files_list(params: TagListInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/business/{slug}/files/",
        params={"search": args.query},
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=FileSummary,
    )


@tool(
    name="bookkeeping_file_retrieve",
    tags={ToolTag.READ_ONLY.value},
    description="Retrieve uploaded file metadata by file_id from bookkeeping_files_list.",
)
async def bookkeeping_file_retrieve(params: IdInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    result = await get_client().request(
        "GET", f"/v1/business/{slug}/files/{args.id}/", business_slug=slug
    )
    return dump_model_from_backend(FileSummary, result)


@tool(
    name="bookkeeping_file_update",
    description="Update uploaded file metadata by file_id from bookkeeping_files_list.",
)
async def bookkeeping_file_update(params: IdPayloadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/business/{slug}/files/{args.id}/"
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(FileSummary, result)


@tool(
    name="bookkeeping_file_delete",
    description="Delete an uploaded file by file_id from bookkeeping_files_list.",
)
async def bookkeeping_file_delete(params: IdInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    path = f"/v1/business/{slug}/files/{args.id}/"
    await get_client().request("DELETE", path, business_slug=slug)
    return dump_model(DeletedResponse(file_id=args.id))


@tool(
    name="bookkeeping_file_upload",
    description="Upload a file attachment from base64 content and return the file handle for follow-up document workflows.",
)
async def bookkeeping_file_upload(params: FileUploadInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    try:
        content = base64.b64decode(args.file_base64)
    except ValueError:
        raise_tool_error("validation_error", "file_base64 is not valid base64.")
    path = f"/v1/business/{slug}/file_upload/"
    result = await get_client().request_multipart(
        path,
        files={"file": (args.filename, content, args.content_type)},
        data={"name": args.filename, "type": args.content_type},
        business_slug=slug,
    )
    return dump_model_from_backend(FileSummary, result)


def _is_duplicate_tag_name_error(exc: ToolError) -> bool:
    try:
        payload = json.loads(str(exc))
    except Exception:
        return False
    return _contains_duplicate_tag_name_error(payload)


def _contains_duplicate_tag_name_error(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "name" and _contains_duplicate_tag_name_error(nested):
                return True
            if _contains_duplicate_tag_name_error(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_duplicate_tag_name_error(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return "already in use" in lowered or "käytössä" in lowered
    return False
