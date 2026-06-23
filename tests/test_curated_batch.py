from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.bookkeeping.account import (
    bookkeeping_account_delete,
    bookkeeping_account_update,
)
from nocfo_toolkit.mcp.curated.bookkeeping.document import bookkeeping_document_delete
from nocfo_toolkit.mcp.curated.bookkeeping.tag_file import (
    bookkeeping_document_tags_update,
    bookkeeping_tag_create,
)
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    AccountNumbersInput,
    AccountNumbersPayloadInput,
    DocumentTagsBatchInput,
    PayloadsInput,
    SalesInvoiceTargetsInput,
    ToolHandlesInput,
)
from nocfo_toolkit.mcp.curated.utils import encode_tool_handle


def _stub_account_client(calls: list, *, failing_numbers: set[int] | None = None):
    failing_numbers = failing_numbers or set()

    async def _resolve_id(
        list_path: str,
        *,
        lookup_field: str,
        lookup_value: object,
        business_slug: str,
        search_param: str | None = None,
    ) -> int:
        number = int(lookup_value)
        if number in failing_numbers:
            raise_tool_error("not_found", f"No account {number}.", status_code=404)
        return number * 10

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        calls.append((method, path, json_body))
        return {"number": int(path.rstrip("/").split("/")[-1]) // 10}

    return SimpleNamespace(resolve_id=_resolve_id, request=_request)


def _run_account_tool(tool, params, calls, *, failing_numbers=None):
    async def _slug(_: str) -> str:
        return "demo"

    with (
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.account.business_slug",
            _slug,
        ),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.account.get_client",
            return_value=_stub_account_client(calls, failing_numbers=failing_numbers),
        ),
    ):
        return asyncio.run(tool(params))


def test_batch_update_applies_shared_payload_to_every_target() -> None:
    calls: list = []
    params = AccountNumbersPayloadInput(
        business="demo", account_numbers=[1910, 2000], payload={"name": "Renamed"}
    )
    result = _run_account_tool(bookkeeping_account_update, params, calls)

    assert result["total"] == 2
    assert result["succeeded"] == 2
    assert result["failed"] == 0
    patched = [c for c in calls if c[0] == "PATCH"]
    assert len(patched) == 2
    assert all(c[2] == {"name": "Renamed"} for c in patched)


def test_batch_delete_runs_once_per_target() -> None:
    calls: list = []
    params = AccountNumbersInput(business="demo", account_numbers=[1910, 2000, 3000])
    result = _run_account_tool(bookkeeping_account_delete, params, calls)

    assert result["total"] == 3
    assert result["succeeded"] == 3
    assert [c[0] for c in calls] == ["DELETE", "DELETE", "DELETE"]
    assert [item["target"] for item in result["results"]] == [1910, 2000, 3000]


def test_batch_continues_after_a_failing_target() -> None:
    calls: list = []
    params = AccountNumbersInput(business="demo", account_numbers=[1910, 9999, 3000])
    result = _run_account_tool(
        bookkeeping_account_delete, params, calls, failing_numbers={9999}
    )

    assert result["total"] == 3
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    failed = [item for item in result["results"] if not item["ok"]]
    assert len(failed) == 1
    assert failed[0]["target"] == 9999
    assert failed[0]["error"]["error_type"] == "not_found"
    # The other two targets still executed their DELETE.
    assert len([c for c in calls if c[0] == "DELETE"]) == 2


def test_single_scalar_is_coerced_to_one_item_batch() -> None:
    calls: list = []
    params = AccountNumbersInput(business="demo", account_numbers=1910)
    result = _run_account_tool(bookkeeping_account_delete, params, calls)

    assert result["total"] == 1
    assert result["results"][0]["target"] == 1910


def test_run_batch_rejects_empty_targets() -> None:
    async def _handler(_target):
        raise AssertionError("handler should not run for an empty batch")

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(run_batch([], _handler))

    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "invalid_request"


def test_run_batch_captures_unexpected_non_toolerror() -> None:
    # A non-ToolError (e.g. response-validation or transport error) on one target
    # must be isolated as a failed item, not abort the whole best-effort batch.
    async def _handler(target):
        if target == 2:
            raise ValueError("boom")
        return {"target": target}

    result = asyncio.run(run_batch([1, 2, 3], _handler))

    assert result["total"] == 3
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    failed = [item for item in result["results"] if not item["ok"]]
    assert failed[0]["target"] == 2
    assert failed[0]["error"]["error_type"] == "internal_error"
    assert "boom" in failed[0]["error"]["message"]


def test_run_batch_isolates_a_raising_label() -> None:
    # A misbehaving label callable must neither abort the batch nor flip a
    # successful target into a failure; the key just falls back to None.
    def _label(_target):
        raise RuntimeError("label boom")

    async def _handler(target):
        return {"value": target}

    result = asyncio.run(run_batch([1, 2], _handler, label=_label))

    assert result["succeeded"] == 2
    assert result["failed"] == 0
    assert all("target" not in item for item in result["results"])


def test_payloads_input_coerces_single_dict_to_one_item() -> None:
    params = PayloadsInput.model_validate({"payloads": {"name": "x"}})
    assert params.payloads == [{"name": "x"}]


def test_sales_invoice_targets_require_exactly_one_selector() -> None:
    SalesInvoiceTargetsInput(business="demo", invoice_numbers=[1])
    SalesInvoiceTargetsInput(business="demo", tool_handles=["h"])
    with pytest.raises(ValueError):
        SalesInvoiceTargetsInput(business="demo")
    with pytest.raises(ValueError):
        SalesInvoiceTargetsInput(
            business="demo", invoice_numbers=[1], tool_handles=["h"]
        )


def test_document_tags_update_applies_shared_tags_to_each_handle() -> None:
    calls: list = []

    async def _resolve_id(
        list_path, *, lookup_field, lookup_value, business_slug, search_param=None
    ):
        return {"VAT": 11, "Travel": 22}[lookup_value]

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        calls.append((method, path, json_body))
        return {"id": int(path.rstrip("/").split("/")[-1]), "number": "BK-1"}

    client = SimpleNamespace(resolve_id=_resolve_id, request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = DocumentTagsBatchInput(
        business="demo",
        tool_handles=[
            encode_tool_handle("bookkeeping_document", 5),
            encode_tool_handle("bookkeeping_document", 6),
        ],
        tag_names=["VAT", "Travel"],
    )
    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.tag_file.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.tag_file.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(bookkeeping_document_tags_update(params))

    assert result["succeeded"] == 2
    patched = [c for c in calls if c[0] == "PATCH"]
    assert [c[1] for c in patched] == [
        "/v1/business/demo/document/5/",
        "/v1/business/demo/document/6/",
    ]
    assert all(c[2] == {"tag_ids": [11, 22]} for c in patched)


def test_tag_create_batch_recovers_existing_tag_on_duplicate_name() -> None:
    async def _resolve_id(
        list_path, *, lookup_field, lookup_value, business_slug, search_param=None
    ):
        return 99  # existing tag id for the duplicate name

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        if method == "POST" and json_body and json_body.get("name") == "Dup":
            raise ToolError(
                json.dumps(
                    {
                        "error_type": "validation_error",
                        "message": "name already in use",
                        "name": ["already in use"],
                    }
                )
            )
        if method == "POST":
            return {"id": 1, "name": json_body["name"]}
        return {"id": 99, "name": "Dup"}  # GET of the existing tag

    client = SimpleNamespace(resolve_id=_resolve_id, request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = PayloadsInput(business="demo", payloads=[{"name": "New"}, {"name": "Dup"}])
    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.tag_file.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.tag_file.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(bookkeeping_tag_create(params))

    assert result["succeeded"] == 2
    dup_item = next(item for item in result["results"] if item["target"] == "Dup")
    assert dup_item["result"]["id"] == 99


def test_document_delete_batch_runs_once_per_handle() -> None:
    calls: list = []

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        calls.append((method, path))
        if method == "GET":
            return {"id": int(path.rstrip("/").split("/")[-1]), "number": "BK-9"}
        return None

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = ToolHandlesInput(
        business="demo",
        tool_handles=[
            encode_tool_handle("bookkeeping_document", 5),
            encode_tool_handle("bookkeeping_document", 6),
        ],
    )
    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.document.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(bookkeeping_document_delete(params))

    assert result["succeeded"] == 2
    assert [c for c in calls if c[0] == "DELETE"] == [
        ("DELETE", "/v1/business/demo/document/5/"),
        ("DELETE", "/v1/business/demo/document/6/"),
    ]
