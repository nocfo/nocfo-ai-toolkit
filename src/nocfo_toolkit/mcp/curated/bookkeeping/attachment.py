"""Read tool for files suggested as attachments for a bookkeeping document.

Attaching/detaching files is done via bookkeeping_documents_bulk_edit (the
add_attachments/remove_attachments/set_attachments edits, one group per document for
different files per document). This module exposes the read side: which uploaded
files likely belong to a document so the agent can review and decide before attaching.
"""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations

from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    DocumentRetrieveInput,
    FileSummary,
    ItemsResponse,
    dump_model,
    dump_models,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle, items


@tool(
    name="bookkeeping_document_suggested_attachments_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="List uploaded files that likely belong to a bookkeeping document but are not yet attached, matched by amount, date, and contact. Each candidate carries its detected date and total amount (analysis_badges) for quick triage; for the full recognized content (merchant/contact, document type, payment reference) call bookkeeping_file_retrieve on a candidate's id. Confirm a file truly belongs, then attach it with bookkeeping_documents_bulk_edit (an add_attachments edit, one group per document). Pass the document tool_handle from bookkeeping_documents_list or bookkeeping_document_retrieve.",
    output_schema=ItemsResponse.model_json_schema(),
)
async def bookkeeping_document_suggested_attachments_list(
    params: DocumentRetrieveInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    document_id = decode_tool_handle(
        params.tool_handle, expected_resource="bookkeeping_document"
    )
    payload = await get_client().request(
        "GET",
        f"/v1/business/{slug}/document/{document_id}/suggest_attachments/",
        business_slug=slug,
    )
    raw = payload if isinstance(payload, list) else items(payload)
    return dump_model(ItemsResponse(items=dump_models(FileSummary, raw)))
