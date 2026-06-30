"""Bookkeeping tag and file MCP tools."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    DeletedResponse,
    DocumentSummary,
    DocumentTagsBatchInput,
    FileDetail,
    FileSummary,
    FileUploadSpec,
    FileUploadsInput,
    IdInput,
    IdsInput,
    IdUpdateItem,
    IdUpdatesInput,
    TagSummary,
    TagListInput,
    PayloadsInput,
    ListEnvelope,
    dump_model,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle


@tool(
    name="bookkeeping_tags_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List business tags used across bookkeeping documents and invoices, and as tag filters in reporting. Use this first to ground exact tag IDs/names before updating, deleting, or applying tags.",
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
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Create one or more business tags in a single call — pass each new tag as an entry in payloads. Tags can be reused across documents and invoices, and for report filtering. Apply them to documents with bookkeeping_document_tags_update.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_tag_create(params: PayloadsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/business/{slug}/tags/"

    async def _create(payload: dict[str, Any]) -> dict[str, Any]:
        tag_name = str(payload.get("name") or "").strip()
        try:
            result = await get_client().request(
                "POST", path, json_body=payload, business_slug=slug
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

    return await run_batch(
        params.payloads, _create, label=lambda payload: payload.get("name")
    )


@tool(
    name="bookkeeping_tag_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve one business tag by tag_id from bookkeeping_tags_list. Use this to verify a tag before updating or deleting it.",
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
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Update one or more business tags in a single confirmed call — pass each update (id + the fields to change for THAT tag) as an entry in updates. Different tags can get different changes in one call. Ground the exact tag IDs first.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_tag_update(params: IdUpdatesInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(item: IdUpdateItem) -> dict[str, Any]:
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/tags/{item.id}/",
            json_body=item.payload,
            business_slug=slug,
        )
        return dump_model_from_backend(TagSummary, result)

    return await run_batch(params.updates, _update, label=lambda item: item.id)


@tool(
    name="bookkeeping_tag_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more business tags in a single call — pass every target in ids. Ground the exact tag IDs first with bookkeeping_tags_list and/or bookkeeping_tag_retrieve, then batch all confirmed targets into one call. Never call this with guessed placeholders or an empty target set. Prefer one batched call over repeated single-target calls (each call needs its own confirmation).",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_tag_delete(params: IdsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(tag_id: int) -> dict[str, Any]:
        await get_client().request(
            "DELETE", f"/v1/business/{slug}/tags/{tag_id}/", business_slug=slug
        )
        return dump_model(DeletedResponse(tag_id=tag_id))

    return await run_batch(params.ids, _delete)


@tool(
    name="bookkeeping_document_tags_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Replace the tags of one or more documents selected by tool_handles; the same tag_names are applied to every target. First obtain the exact document tool_handles from bookkeeping_documents_list or bookkeeping_document_retrieve, and use shared business tags from bookkeeping_tags_list. Tag names must already exist; create missing tags first with bookkeeping_tag_create. Prefer one batched call over repeated single-document tag updates.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_document_tags_update(
    params: DocumentTagsBatchInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    tag_ids = []
    for name in params.tag_names:
        tag_ids.append(
            await get_client().resolve_id(
                f"/v1/business/{slug}/tags/",
                lookup_field="name",
                lookup_value=name,
                search_param="search",
                business_slug=slug,
            )
        )

    async def _apply(handle: str) -> dict[str, Any]:
        document_id = decode_tool_handle(
            handle, expected_resource="bookkeeping_document"
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/document/{document_id}/",
            json_body={"tag_ids": tag_ids},
            business_slug=slug,
        )
        return dump_model_from_backend(DocumentSummary, result)

    return await run_batch(params.tool_handles, _apply)


@tool(
    name="bookkeeping_files_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List uploaded files/attachments metadata. Use this first to ground exact file IDs before updating or deleting files.",
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
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Retrieve full detail for one uploaded file by file_id, including the recognized content extracted from it (analysis: detected document type, contact/merchant, total amount, dates, due date, payment reference) plus its analysis status. Use this to inspect what a file actually is — comparing its recognized fields against a document's contact, date, amount, and blueprint — before deleting it or attaching it to a document.",
)
async def bookkeeping_file_retrieve(params: IdInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    result = await get_client().request(
        "GET", f"/v1/business/{slug}/files/{args.id}/", business_slug=slug
    )
    detail = dict(result) if isinstance(result, dict) else {}
    detail["analysis"] = _flatten_file_analysis(detail.get("analysis_results"))
    return dump_model_from_backend(FileDetail, detail)


@tool(
    name="bookkeeping_file_update",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Update standalone metadata of one or more uploaded files in a single confirmed call — pass each update (id + the fields to change for THAT file, e.g. name or folder) as an entry in updates; different files can get different changes. This does NOT attach files to documents or change which files a document has. To attach or detach a document's files, use bookkeeping_documents_bulk_edit (an add_attachments/remove_attachments edit, one group per document) or pass attachment_ids to bookkeeping_document_create/bookkeeping_document_update. Ground the exact file IDs first with bookkeeping_files_list.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_file_update(params: IdUpdatesInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(item: IdUpdateItem) -> dict[str, Any]:
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/files/{item.id}/",
            json_body=item.payload,
            business_slug=slug,
        )
        return dump_model_from_backend(FileSummary, result)

    return await run_batch(params.updates, _update, label=lambda item: item.id)


@tool(
    name="bookkeeping_file_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more uploaded files in a single call — pass every target in ids. Ground the exact file IDs first with bookkeeping_files_list and/or bookkeeping_file_retrieve, then batch all confirmed targets into one call. Never call this with guessed placeholders or an empty target set. Prefer one batched call over repeated single-target calls (each call needs its own confirmation).",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_file_delete(params: IdsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(file_id: int) -> dict[str, Any]:
        await get_client().request(
            "DELETE", f"/v1/business/{slug}/files/{file_id}/", business_slug=slug
        )
        return dump_model(DeletedResponse(file_id=file_id))

    return await run_batch(params.ids, _delete)


@tool(
    name="bookkeeping_file_upload",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Upload one or more file attachments from base64 content in a single call — pass each file as an entry in files. Returns the new file ids. To attach an uploaded file to a bookkeeping document, first review it with bookkeeping_file_retrieve, then attach by id with bookkeeping_documents_bulk_edit (an add_attachments edit, one group per document) or by passing attachment_ids to bookkeeping_document_create/bookkeeping_document_update.",
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_file_upload(params: FileUploadsInput) -> dict[str, Any]:
    slug = await business_slug(params.business)
    path = f"/v1/business/{slug}/file_upload/"

    async def _upload(spec: FileUploadSpec) -> dict[str, Any]:
        try:
            content = base64.b64decode(spec.file_base64)
        except ValueError:
            raise_tool_error("validation_error", "file_base64 is not valid base64.")
        result = await get_client().request_multipart(
            path,
            files={"file": (spec.filename, content, spec.content_type)},
            data={"name": spec.filename, "type": spec.content_type},
            business_slug=slug,
        )
        return dump_model_from_backend(FileSummary, result)

    return await run_batch(params.files, _upload, label=lambda spec: spec.filename)


def _flatten_file_analysis(analysis_results: Any) -> dict[str, Any] | None:
    """Flatten backend content-analysis blocks into a {type: value} dict.

    The file detail returns ``analysis_results`` as a list of blocks, each holding
    ``values`` of ``{type, value}`` recognized fields (merchant, total, dates, etc.).
    Flatten to a compact, agent-readable mapping for attach decisions.
    """
    if not isinstance(analysis_results, list):
        return None
    flat: dict[str, Any] = {}
    for block in analysis_results:
        if not isinstance(block, dict):
            continue
        values = block.get("values")
        rows = values if isinstance(values, list) else [block]
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = row.get("type")
            if key is not None and key not in flat:
                flat[key] = row.get("value")
    return flat or None


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
