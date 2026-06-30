from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.bookkeeping.bulk_edit import (
    bookkeeping_documents_bulk_edit,
)
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import DocumentBulkEditInput
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle, encode_tool_handle


def _handle(document_id: int) -> str:
    return encode_tool_handle("bookkeeping_document", document_id)


class _StubClient:
    """Minimal CuratedNocfoClient stand-in for the bulk-edit tool."""

    def __init__(
        self,
        *,
        documents: dict[int, dict[str, Any]],
        account_ids: dict[int, int] | None = None,
        tag_ids: dict[str, int] | None = None,
        contact_ids: dict[str, int] | None = None,
        list_pages: list[dict[str, Any]] | None = None,
        list_by_account: dict[int, list[dict[str, Any]]] | None = None,
        fail_patch_ids: set[int] | None = None,
    ) -> None:
        self.documents = documents
        self.account_ids = account_ids or {}
        self.tag_ids = tag_ids or {}
        self.contact_ids = contact_ids or {}
        self.list_pages = list_pages
        self.list_by_account = list_by_account
        self.fail_patch_ids = fail_patch_ids or set()
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    async def resolve_id(
        self,
        list_path: str,
        *,
        lookup_field: str,
        lookup_value: Any,
        business_slug: str,
        search_param: str | None = None,
    ) -> int:
        if "/account/" in list_path:
            return self.account_ids[int(lookup_value)]
        if "/tags/" in list_path:
            return self.tag_ids[lookup_value]
        if "/contacts/" in list_path:
            return self.contact_ids[lookup_value]
        raise AssertionError(f"unexpected resolve_id path {list_path}")

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        business_slug: str | None = None,
    ) -> Any:
        self.calls.append((method, path, params, json_body))
        if method == "GET" and path.endswith("/document/"):
            if self.list_by_account is not None:
                account = (params or {}).get("account")
                return {"results": self.list_by_account.get(account, []), "next": None}
            page = int((params or {}).get("page", 1))
            if self.list_pages is not None:
                return self.list_pages[page - 1]
            return {"results": [], "next": None}
        if method == "GET":
            document_id = int(path.rstrip("/").split("/")[-1])
            return self.documents[document_id]
        if method == "PATCH":
            document_id = int(path.rstrip("/").split("/")[-1])
            if document_id in self.fail_patch_ids:
                raise_tool_error("locked", "Document is locked.", status_code=423)
            return {**self.documents[document_id], **(json_body or {})}
        raise AssertionError(f"unexpected request {method} {path}")


def _run(params: DocumentBulkEditInput, client: _StubClient) -> dict[str, Any]:
    async def _slug(_: str) -> str:
        return "demo"

    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.bulk_edit.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.bulk_edit.get_client",
            return_value=client,
        ),
    ):
        return asyncio.run(bookkeeping_documents_bulk_edit(params))


def _patches(client: _StubClient) -> list[tuple[str, dict | None]]:
    return [
        (path, body)
        for method, path, _params, body in client.calls
        if method == "PATCH"
    ]


def _doc(document_id: int, blueprint: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "id": document_id,
        "number": f"BK-{document_id}",
        "blueprint": blueprint,
        **extra,
    }


def test_replace_account_swaps_shortcut_and_rows_and_preserves_others() -> None:
    client = _StubClient(
        documents={
            5: _doc(
                5,
                {"debet_account_id": 10, "credit_account_id": 20, "credit_entries": []},
            ),
            6: _doc(
                6,
                {
                    "debet_account_id": None,
                    "credit_account_id": 20,
                    "debet_entries": [{"account_id": 10, "amount": 100}],
                },
            ),
        },
        account_ids={1910: 10, 1031: 31},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5), _handle(6)],
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    result = _run(params, client)

    assert result["succeeded"] == 2
    assert result["failed"] == 0
    patched = dict(_patches(client))
    assert (
        patched["/v1/business/demo/document/5/"]["blueprint"]["debet_account_id"] == 31
    )
    # Untouched accounts on the same document are preserved.
    assert (
        patched["/v1/business/demo/document/5/"]["blueprint"]["credit_account_id"] == 20
    )
    assert (
        patched["/v1/business/demo/document/6/"]["blueprint"]["debet_entries"][0][
            "account_id"
        ]
        == 31
    )


def test_replace_account_without_selector_derives_targets_from_edit() -> None:
    client = _StubClient(
        documents={
            5: _doc(5, {"debet_account_id": 10, "credit_entries": []}),
            6: _doc(6, {"debet_account_id": 10, "credit_entries": []}),
        },
        account_ids={1910: 10, 1031: 31},
        list_pages=[{"results": [{"id": 5}, {"id": 6}], "next": None}],
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    result = _run(params, client)

    assert result["total"] == 2
    # The document list was queried by the resolved account id.
    list_calls = [
        c for c in client.calls if c[0] == "GET" and c[1].endswith("/document/")
    ]
    assert list_calls[0][2]["account"] == 10
    assert len(_patches(client)) == 2


def test_multi_source_auto_select_fetches_every_replaced_account() -> None:
    # Two replace_account edits with NO selector must target documents for BOTH
    # source accounts (not just the first), and union them.
    client = _StubClient(
        documents={
            5: _doc(5, {"debet_account_id": 10, "credit_entries": []}),
            6: _doc(6, {"debet_account_id": 20, "credit_entries": []}),
        },
        account_ids={1910: 10, 1031: 31, 1920: 20, 1040: 40},
        list_by_account={10: [{"id": 5}], 20: [{"id": 6}]},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031},
                {"op": "replace_account", "from_account": 1920, "to_account": 1040},
            ],
        }
    )
    result = _run(params, client)

    assert result["total"] == 2
    # Both source accounts were queried, and both documents were updated.
    queried_accounts = {
        c[2]["account"]
        for c in client.calls
        if c[0] == "GET" and c[1].endswith("/document/")
    }
    assert queried_accounts == {10, 20}
    patched = dict(_patches(client))
    assert (
        patched["/v1/business/demo/document/5/"]["blueprint"]["debet_account_id"] == 31
    )
    assert (
        patched["/v1/business/demo/document/6/"]["blueprint"]["debet_account_id"] == 40
    )


def test_too_many_matching_documents_raises_instead_of_silent_partial() -> None:
    # A selection larger than the pagination cap must fail loudly, not silently
    # apply the change to only the first page-cap of matches.
    async def _resolve_id(
        list_path, *, lookup_field, lookup_value, business_slug, search_param=None
    ):
        return 10

    async def _request(
        method, path, *, params=None, json_body=None, business_slug=None
    ):
        # Every page claims there is another page → exceeds _MAX_PAGES.
        return {"results": [{"id": 1}], "next": "more"}

    client = SimpleNamespace(resolve_id=_resolve_id, request=_request)
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    with pytest.raises(ToolError) as exc_info:
        _run(params, client)
    assert json.loads(str(exc_info.value))["error_type"] == "too_many_documents"


def test_uniform_mode_accepts_a_single_scalar_tool_handle() -> None:
    # A lone top-level tool_handle must coerce to a one-item list (like per-group).
    client = _StubClient(
        documents={5: _doc(5, {"debet_account_id": 10, "credit_entries": []})},
        account_ids={1910: 10, 1031: 31},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": _handle(5),
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    assert params.tool_handles == [_handle(5)]
    result = _run(params, client)
    assert result["succeeded"] == 1


def test_paginates_through_all_matching_documents() -> None:
    client = _StubClient(
        documents={
            5: _doc(5, {"debet_account_id": 10, "credit_entries": []}),
            6: _doc(6, {"debet_account_id": 10, "credit_entries": []}),
        },
        account_ids={1910: 10, 1031: 31},
        list_pages=[
            {"results": [{"id": 5}], "next": "more"},
            {"results": [{"id": 6}], "next": None},
        ],
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "account_number": 1910,
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    result = _run(params, client)

    assert result["total"] == 2
    list_calls = [
        c for c in client.calls if c[0] == "GET" and c[1].endswith("/document/")
    ]
    assert [c[2]["page"] for c in list_calls] == [1, 2]
    # account_number filter is resolved to the backend `account` id param.
    assert all(c[2]["account"] == 10 for c in list_calls)


def test_no_matching_value_skips_patch_and_reports_no_change() -> None:
    client = _StubClient(
        documents={7: _doc(7, {"debet_account_id": 99, "credit_entries": []})},
        account_ids={1910: 10, 1031: 31},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(7)],
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    result = _run(params, client)

    assert result["succeeded"] == 1
    assert result["results"][0]["result"]["changed"] is False
    assert _patches(client) == []


def test_add_tags_unions_with_existing_tags() -> None:
    client = _StubClient(
        documents={5: _doc(5, {"debet_account_id": 10}, tag_ids=[1, 2])},
        tag_ids={"VAT": 9},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5)],
            "edits": [{"op": "add_tags", "tag_names": ["VAT"]}],
        }
    )
    _run(params, client)
    assert dict(_patches(client))["/v1/business/demo/document/5/"] == {
        "tag_ids": [1, 2, 9]
    }


def test_remove_tags_keeps_other_tags() -> None:
    client = _StubClient(
        documents={5: _doc(5, {"debet_account_id": 10}, tag_ids=[1, 2])},
        tag_ids={"Travel": 2},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5)],
            "edits": [{"op": "remove_tags", "tag_names": ["Travel"]}],
        }
    )
    _run(params, client)
    assert dict(_patches(client))["/v1/business/demo/document/5/"] == {"tag_ids": [1]}


def test_set_tags_replaces_full_set() -> None:
    client = _StubClient(
        documents={5: _doc(5, {"debet_account_id": 10}, tag_ids=[1, 2])},
        tag_ids={"Only": 7},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5)],
            "edits": [{"op": "set_tags", "tag_names": ["Only"]}],
        }
    )
    _run(params, client)
    assert dict(_patches(client))["/v1/business/demo/document/5/"] == {"tag_ids": [7]}


def test_replace_vat_code_sets_code_and_rate_on_matching_rows() -> None:
    client = _StubClient(
        documents={
            5: _doc(
                5,
                {
                    "debet_account_id": 10,
                    "credit_entries": [
                        {
                            "account_id": 30,
                            "vat_code": 24,
                            "vat_rate": 24,
                            "amount": 100,
                        },
                        {"account_id": 30, "vat_code": 0, "vat_rate": 0, "amount": 50},
                    ],
                },
            )
        },
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5)],
            "edits": [
                {
                    "op": "replace_vat_code",
                    "from_vat_code": 24,
                    "to_vat_code": 0,
                    "to_vat_rate": 0,
                }
            ],
        }
    )
    _run(params, client)
    rows = dict(_patches(client))["/v1/business/demo/document/5/"]["blueprint"][
        "credit_entries"
    ]
    assert rows[0]["vat_code"] == 0
    assert rows[0]["vat_rate"] == 0
    # The already-tax-free row stays untouched.
    assert rows[1]["vat_code"] == 0


def test_combined_edits_apply_in_one_patch_per_document() -> None:
    client = _StubClient(
        documents={
            5: _doc(5, {"debet_account_id": 10, "credit_entries": []}, tag_ids=[1])
        },
        account_ids={1910: 10, 1031: 31},
        tag_ids={"Reviewed": 9},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5)],
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031},
                {"op": "add_tags", "tag_names": ["Reviewed"]},
            ],
        }
    )
    _run(params, client)
    patches = _patches(client)
    assert len(patches) == 1
    body = patches[0][1]
    assert body["blueprint"]["debet_account_id"] == 31
    assert body["tag_ids"] == [1, 9]


def test_locked_document_is_reported_as_failed_not_fatal() -> None:
    client = _StubClient(
        documents={
            5: _doc(5, {"debet_account_id": 10, "credit_entries": []}),
            6: _doc(6, {"debet_account_id": 10, "credit_entries": []}),
        },
        account_ids={1910: 10, 1031: 31},
        fail_patch_ids={6},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5), _handle(6)],
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    result = _run(params, client)

    assert result["succeeded"] == 1
    assert result["failed"] == 1
    failed = [item for item in result["results"] if not item["ok"]][0]
    assert (
        decode_tool_handle(failed["target"], expected_resource="bookkeeping_document")
        == 6
    )
    assert failed["error"]["error_type"] == "locked"


def test_empty_match_raises_not_found() -> None:
    client = _StubClient(
        documents={},
        account_ids={1910: 10, 1031: 31},
        list_pages=[{"results": [], "next": None}],
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "edits": [
                {"op": "replace_account", "from_account": 1910, "to_account": 1031}
            ],
        }
    )
    with pytest.raises(ToolError) as exc_info:
        _run(params, client)
    assert json.loads(str(exc_info.value))["error_type"] == "not_found"


def test_tool_handles_with_filters_is_rejected() -> None:
    client = _StubClient(documents={5: _doc(5, {"debet_account_id": 10})})
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "tool_handles": [_handle(5)],
            "account_number": 1910,
            "edits": [{"op": "set_date", "date": "2026-01-01"}],
        }
    )
    with pytest.raises(ToolError) as exc_info:
        _run(params, client)
    assert json.loads(str(exc_info.value))["error_type"] == "invalid_request"


def test_unselectable_edit_without_selector_is_rejected() -> None:
    client = _StubClient(documents={}, tag_ids={"X": 9})
    params = DocumentBulkEditInput.model_validate(
        {"business": "demo", "edits": [{"op": "add_tags", "tag_names": ["X"]}]}
    )
    with pytest.raises(ToolError) as exc_info:
        _run(params, client)
    assert json.loads(str(exc_info.value))["error_type"] == "invalid_request"


def test_replace_account_rejects_identical_accounts() -> None:
    with pytest.raises(ValueError):
        DocumentBulkEditInput.model_validate(
            {
                "business": "demo",
                "tool_handles": [_handle(5)],
                "edits": [
                    {"op": "replace_account", "from_account": 1910, "to_account": 1910}
                ],
            }
        )


def test_per_target_groups_apply_different_edits_per_document() -> None:
    # The canonical heterogeneous case: a different account target per document,
    # all in one call/one confirmation.
    client = _StubClient(
        documents={
            1: _doc(1, {"debet_account_id": 100, "credit_entries": []}),
            2: _doc(2, {"debet_account_id": 100, "credit_entries": []}),
            5: _doc(5, {"debet_account_id": 100, "credit_entries": []}),
            6: _doc(6, {"debet_account_id": 100, "credit_entries": []}),
            7: _doc(7, {"debet_account_id": 100, "credit_entries": []}),
        },
        account_ids={1000: 100, 1090: 190, 3009: 390, 1091: 191},
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "documents": [
                {
                    "tool_handles": [_handle(1)],
                    "edits": [
                        {
                            "op": "replace_account",
                            "from_account": 1000,
                            "to_account": 1090,
                        }
                    ],
                },
                {
                    "tool_handles": [_handle(2)],
                    "edits": [
                        {
                            "op": "replace_account",
                            "from_account": 1000,
                            "to_account": 3009,
                        }
                    ],
                },
                {
                    "tool_handles": [_handle(5), _handle(6), _handle(7)],
                    "edits": [
                        {
                            "op": "replace_account",
                            "from_account": 1000,
                            "to_account": 1091,
                        }
                    ],
                },
            ],
        }
    )
    result = _run(params, client)

    assert result["total"] == 5
    assert result["succeeded"] == 5
    patched = dict(_patches(client))
    assert (
        patched["/v1/business/demo/document/1/"]["blueprint"]["debet_account_id"] == 190
    )
    assert (
        patched["/v1/business/demo/document/2/"]["blueprint"]["debet_account_id"] == 390
    )
    assert (
        patched["/v1/business/demo/document/7/"]["blueprint"]["debet_account_id"] == 191
    )


def test_per_target_attaches_different_file_to_each_document() -> None:
    # The production attachment case: doc 7 <- file 22, doc 6 <- file 23, one call.
    client = _StubClient(
        documents={
            7: _doc(7, {"debet_account_id": 10}, attachment_ids=[]),
            6: _doc(6, {"debet_account_id": 10}, attachment_ids=[]),
        }
    )
    params = DocumentBulkEditInput.model_validate(
        {
            "business": "demo",
            "documents": [
                {
                    "tool_handles": [_handle(7)],
                    "edits": [{"op": "add_attachments", "file_ids": [22]}],
                },
                {
                    "tool_handles": [_handle(6)],
                    "edits": [{"op": "add_attachments", "file_ids": [23]}],
                },
            ],
        }
    )
    result = _run(params, client)

    assert result["total"] == 2
    assert result["succeeded"] == 2
    patched = dict(_patches(client))
    assert patched["/v1/business/demo/document/7/"] == {"attachment_ids": [22]}
    assert patched["/v1/business/demo/document/6/"] == {"attachment_ids": [23]}


def test_rejects_both_modes() -> None:
    with pytest.raises(ValueError):
        DocumentBulkEditInput.model_validate(
            {
                "business": "demo",
                "documents": [
                    {
                        "tool_handles": [_handle(1)],
                        "edits": [{"op": "set_date", "date": "2026-01-01"}],
                    }
                ],
                "edits": [{"op": "set_date", "date": "2026-01-01"}],
            }
        )


def test_rejects_neither_mode() -> None:
    with pytest.raises(ValueError):
        DocumentBulkEditInput.model_validate({"business": "demo"})


def test_per_target_rejects_top_level_filters() -> None:
    with pytest.raises(ValueError):
        DocumentBulkEditInput.model_validate(
            {
                "business": "demo",
                "account_number": 1910,
                "documents": [
                    {
                        "tool_handles": [_handle(1)],
                        "edits": [{"op": "set_date", "date": "2026-01-01"}],
                    }
                ],
            }
        )
