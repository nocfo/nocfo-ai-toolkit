"""General bulk document-edit MCP tool.

``bookkeeping_document_update`` applies one identical payload to every target, so it
cannot express edits that differ per document, or that are derived from each
document's own content. This tool computes a per-document PATCH and applies them all
in one confirmed call. It supports two shapes:

* per-target (``documents``): each group carries its own documents and edits, so
  different documents get different edits.
* uniform (``edits`` + selector): the same edits applied to every matched document.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations

from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BatchResponse,
    DocumentBulkEditInput,
    DocumentSummary,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import (
    decode_tool_handle,
    encode_tool_handle,
    items,
)

_ROW_KEYS = ("debet_entries", "credit_entries", "expense_entries")
_MAX_PAGES = 100


@dataclass
class _EditPlan:
    """Edits pre-resolved to ids once, then applied to each document."""

    account_swaps: dict[int, int] = field(default_factory=dict)
    vat_code_swaps: list[tuple[int, int, float | int | None]] = field(
        default_factory=list
    )
    vat_rate_swaps: dict[float, float] = field(default_factory=dict)
    tag_add_ids: list[int] | None = None
    tag_remove_ids: list[int] | None = None
    tag_set_ids: list[int] | None = None
    attachment_add_ids: list[int] | None = None
    attachment_remove_ids: list[int] | None = None
    attachment_set_ids: list[int] | None = None
    contact_id: int | None = None
    set_description: str | None = None
    replace_descriptions: list[tuple[str, str]] = field(default_factory=list)
    set_date: str | None = None


@tool(
    name="bookkeeping_documents_bulk_edit",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Edit one or many bookkeeping documents in a single confirmed call — use this, not "
        "bookkeeping_document_update, whenever a change is derived from each document's current "
        "content or differs per document. Edits include: replace an account wherever it appears "
        "(e.g. 'change account 1910 to 1031'), swap a VAT code/rate, add/remove/set tags, "
        "add/remove/set file attachments, set contact/date, and set or find-and-replace description "
        "text. Two shapes: (1) `documents` — a list of groups, each with its own tool_handles and "
        "edits, for giving DIFFERENT documents DIFFERENT changes in one confirmation (e.g. document "
        "A's account to 1090, documents B-D's account to 1091, attach file 7 to document A); "
        "(2) `edits` + a selector (tool_handles or filters) — the SAME edits across every matched "
        "document. In uniform mode, if you give edits but no selector, the documents containing the "
        "replaced account/VAT value are targeted automatically. Each edit is computed per document; "
        "locked documents are reported as failed in the per-document BatchResponse. "
        "bookkeeping_document_update remains for setting identical field values on a known handle set."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def bookkeeping_documents_bulk_edit(
    params: DocumentBulkEditInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)
    work = await _build_work(slug, params)
    if not work:
        raise_tool_error(
            "not_found",
            "No documents matched the request.",
            "Provide tool_handles/groups, widen the filters, or include a replace_account/replace_vat edit so matching documents can be found.",
            status_code=404,
        )

    async def _handler(item: tuple[int, _EditPlan]) -> dict[str, Any]:
        return await _edit_one(slug, item[1], item[0])

    return await run_batch(
        work,
        _handler,
        label=lambda item: encode_tool_handle("bookkeeping_document", item[0]),
    )


async def _build_work(
    slug: str, params: DocumentBulkEditInput
) -> list[tuple[int, _EditPlan]]:
    """Resolve the (document_id, plan) units of work for either input shape."""
    if params.documents is not None:
        work: list[tuple[int, _EditPlan]] = []
        for group in params.documents:
            plan = await _compile_plan(slug, group.edits)
            for handle in group.tool_handles:
                document_id = decode_tool_handle(
                    handle, expected_resource="bookkeeping_document"
                )
                work.append((document_id, plan))
        return work

    plan = await _compile_plan(slug, params.edits or [])
    document_ids = await _resolve_uniform_target_ids(slug, params, plan)
    return [(document_id, plan) for document_id in document_ids]


async def _compile_plan(slug: str, edits: list[Any]) -> _EditPlan:
    # Dispatch on the discriminator value `op` (a plain string), not isinstance:
    # FastMCP's FileSystemProvider can reload the schema module, rebinding the edit
    # classes to fresh objects, which would make isinstance checks silently fail.
    plan = _EditPlan()
    for edit in edits:
        op = edit.op
        if op == "replace_account":
            from_id = await _account_id(slug, edit.from_account)
            plan.account_swaps[from_id] = await _account_id(slug, edit.to_account)
        elif op == "replace_vat_code":
            plan.vat_code_swaps.append(
                (edit.from_vat_code, edit.to_vat_code, edit.to_vat_rate)
            )
        elif op == "replace_vat_rate":
            plan.vat_rate_swaps[float(edit.from_vat_rate)] = float(edit.to_vat_rate)
        elif op == "set_contact":
            plan.contact_id = (
                edit.contact_id
                if edit.contact_id is not None
                else await _contact_id(slug, edit.contact or "")
            )
        elif op == "add_tags":
            plan.tag_add_ids = (plan.tag_add_ids or []) + await _tag_ids(
                slug, edit.tag_names
            )
        elif op == "remove_tags":
            plan.tag_remove_ids = (plan.tag_remove_ids or []) + await _tag_ids(
                slug, edit.tag_names
            )
        elif op == "set_tags":
            plan.tag_set_ids = await _tag_ids(slug, edit.tag_names)
        elif op == "add_attachments":
            plan.attachment_add_ids = (plan.attachment_add_ids or []) + list(
                edit.file_ids
            )
        elif op == "remove_attachments":
            plan.attachment_remove_ids = (plan.attachment_remove_ids or []) + list(
                edit.file_ids
            )
        elif op == "set_attachments":
            plan.attachment_set_ids = list(edit.file_ids)
        elif op == "set_description":
            plan.set_description = edit.description
        elif op == "replace_description":
            plan.replace_descriptions.append((edit.find, edit.replace))
        elif op == "set_date":
            plan.set_date = edit.date
    return plan


async def _resolve_uniform_target_ids(
    slug: str, params: DocumentBulkEditInput, plan: _EditPlan
) -> list[int]:
    if params.tool_handles:
        if params.has_filters():
            raise_tool_error(
                "invalid_request",
                "Provide either tool_handles or selection filters, not both.",
                "Pass tool_handles for an explicit set, or filters to select documents.",
                status_code=400,
            )
        return [
            decode_tool_handle(handle, expected_resource="bookkeeping_document")
            for handle in params.tool_handles
        ]

    query = params.filter_params()
    if "account_number" in query:
        query["account"] = await _account_id(slug, query.pop("account_number"))
    if query:
        return await _list_all_document_ids(slug, query)

    # No explicit selector: target every document containing ANY value being
    # replaced. A replace plan can name several source accounts/VAT values, so
    # fetch the union across all of them rather than just the first.
    queries = _derive_queries_from_plan(plan)
    if not queries:
        raise_tool_error(
            "invalid_request",
            "No documents selected.",
            "Pass tool_handles, a filter such as account_number or a date range, or include a "
            "replace_account/replace_vat edit so the matching documents can be found.",
            status_code=400,
        )
    return await _list_union_document_ids(slug, queries)


def _derive_queries_from_plan(plan: _EditPlan) -> list[dict[str, Any]]:
    """One list query per value being replaced (every source, not just the first)."""
    queries: list[dict[str, Any]] = []
    for from_account_id in plan.account_swaps:
        queries.append({"account": from_account_id})
    for from_vat_code, _to_vat_code, _to_vat_rate in plan.vat_code_swaps:
        queries.append({"vat_code": from_vat_code})
    for from_vat_rate in plan.vat_rate_swaps:
        queries.append({"vat_rate": from_vat_rate})
    return queries


async def _list_union_document_ids(
    slug: str, queries: list[dict[str, Any]]
) -> list[int]:
    seen: set[int] = set()
    ids: list[int] = []
    for query in queries:
        for document_id in await _list_all_document_ids(slug, query):
            if document_id not in seen:
                seen.add(document_id)
                ids.append(document_id)
    return ids


async def _list_all_document_ids(slug: str, query: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    page = 1
    while True:
        payload = await get_client().request(
            "GET",
            f"/v1/business/{slug}/document/",
            params={**query, "page": page, "page_size": 100},
            business_slug=slug,
        )
        for item in items(payload):
            raw_id = item.get("id")
            if isinstance(raw_id, int):
                ids.append(raw_id)
        if not (isinstance(payload, dict) and payload.get("next")):
            break
        page += 1
        if page > _MAX_PAGES:
            # Fail loudly instead of silently applying the change to only the first
            # ~_MAX_PAGES*100 matches and reporting it as a complete bulk change.
            raise_tool_error(
                "too_many_documents",
                f"More than {_MAX_PAGES * 100} documents match this selection.",
                "Narrow the request (e.g. add date_from/date_to, or pass an explicit set of "
                "tool_handles) so the change is applied to the full intended set, not just part of it.",
                status_code=400,
            )
    return ids


async def _edit_one(slug: str, plan: _EditPlan, document_id: int) -> dict[str, Any]:
    document = await get_client().request(
        "GET", f"/v1/business/{slug}/document/{document_id}/", business_slug=slug
    )
    document = document if isinstance(document, dict) else {}
    body = _build_patch_body(document, plan)
    if not body:
        summary = dump_model_from_backend(DocumentSummary, document)
        summary["changed"] = False
        summary["note"] = "No matching values to change in this document."
        return summary

    updated = await get_client().request(
        "PATCH",
        f"/v1/business/{slug}/document/{document_id}/",
        json_body=body,
        business_slug=slug,
    )
    summary = dump_model_from_backend(
        DocumentSummary, updated if isinstance(updated, dict) else document
    )
    summary["changed"] = True
    return summary


def _build_patch_body(document: dict[str, Any], plan: _EditPlan) -> dict[str, Any]:
    body: dict[str, Any] = {}

    if plan.account_swaps or plan.vat_code_swaps or plan.vat_rate_swaps:
        blueprint = document.get("blueprint")
        if isinstance(blueprint, dict):
            edited = copy.deepcopy(blueprint)
            changed = _swap_accounts(edited, plan.account_swaps)
            changed = _swap_vat_codes(edited, plan.vat_code_swaps) or changed
            changed = _swap_vat_rates(edited, plan.vat_rate_swaps) or changed
            if changed:
                body["blueprint"] = edited

    current_tags = [
        tag for tag in (document.get("tag_ids") or []) if isinstance(tag, int)
    ]
    new_tags = _apply_id_edits(
        current_tags, plan.tag_add_ids, plan.tag_remove_ids, plan.tag_set_ids
    )
    if new_tags is not None and new_tags != current_tags:
        body["tag_ids"] = new_tags

    current_attachments = [
        att for att in (document.get("attachment_ids") or []) if isinstance(att, int)
    ]
    new_attachments = _apply_id_edits(
        current_attachments,
        plan.attachment_add_ids,
        plan.attachment_remove_ids,
        plan.attachment_set_ids,
    )
    if new_attachments is not None and new_attachments != current_attachments:
        body["attachment_ids"] = new_attachments

    if plan.contact_id is not None and document.get("contact_id") != plan.contact_id:
        body["contact_id"] = plan.contact_id

    new_description = _apply_description_edits(document.get("description"), plan)
    if new_description is not None and new_description != document.get("description"):
        body["description"] = new_description

    if plan.set_date is not None and document.get("date") != plan.set_date:
        body["date"] = plan.set_date

    return body


def _blueprint_rows(blueprint: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for rows_key in _ROW_KEYS:
        rows = blueprint.get(rows_key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield row


def _swap_accounts(blueprint: dict[str, Any], swaps: dict[int, int]) -> bool:
    if not swaps:
        return False
    changed = False
    for key in ("debet_account_id", "credit_account_id"):
        value = blueprint.get(key)
        if isinstance(value, int) and value in swaps:
            blueprint[key] = swaps[value]
            changed = True
    for row in _blueprint_rows(blueprint):
        value = row.get("account_id")
        if isinstance(value, int) and value in swaps:
            row["account_id"] = swaps[value]
            changed = True
    return changed


def _swap_vat_codes(
    blueprint: dict[str, Any], swaps: list[tuple[int, int, float | int | None]]
) -> bool:
    if not swaps:
        return False
    mapping = {from_code: (to_code, to_rate) for from_code, to_code, to_rate in swaps}
    changed = False
    for row in _blueprint_rows(blueprint):
        code = row.get("vat_code")
        if code in mapping:
            to_code, to_rate = mapping[code]
            row["vat_code"] = to_code
            if to_rate is not None:
                row["vat_rate"] = to_rate
            changed = True
    return changed


def _swap_vat_rates(blueprint: dict[str, Any], swaps: dict[float, float]) -> bool:
    if not swaps:
        return False
    changed = False
    for row in _blueprint_rows(blueprint):
        raw = row.get("vat_rate")
        if raw is None:
            continue
        try:
            rate = float(raw)
        except (TypeError, ValueError):
            continue
        if rate in swaps:
            row["vat_rate"] = swaps[rate]
            changed = True
    return changed


def _apply_id_edits(
    current: list[int],
    add_ids: list[int] | None,
    remove_ids: list[int] | None,
    set_ids: list[int] | None,
) -> list[int] | None:
    """Resolve an add/remove/set id-list edit against a document's current ids."""
    if set_ids is not None:
        return list(set_ids)
    if add_ids is None and remove_ids is None:
        return None
    result = list(current)
    for value in add_ids or []:
        if value not in result:
            result.append(value)
    if remove_ids:
        remove = set(remove_ids)
        result = [value for value in result if value not in remove]
    return result


def _apply_description_edits(current: Any, plan: _EditPlan) -> str | None:
    new_value: str | None = None
    if plan.set_description is not None:
        new_value = plan.set_description
    if plan.replace_descriptions:
        base = new_value if new_value is not None else (current or "")
        for find, replace in plan.replace_descriptions:
            base = base.replace(find, replace)
        new_value = base
    return new_value


async def _account_id(slug: str, number: int | str) -> int:
    return await get_client().resolve_id(
        f"/v1/business/{slug}/account/",
        lookup_field="number",
        lookup_value=number,
        business_slug=slug,
    )


async def _tag_ids(slug: str, names: list[str]) -> list[int]:
    return [
        await get_client().resolve_id(
            f"/v1/business/{slug}/tags/",
            lookup_field="name",
            lookup_value=name,
            search_param="search",
            business_slug=slug,
        )
        for name in names
    ]


async def _contact_id(slug: str, name: str) -> int:
    return await get_client().resolve_id(
        f"/v1/business/{slug}/contacts/",
        lookup_field="name",
        lookup_value=name,
        search_param="search",
        business_slug=slug,
    )
