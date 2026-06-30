from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.bookkeeping.account import (
    bookkeeping_account_action,
    bookkeeping_account_delete,
    bookkeeping_account_update,
)
from nocfo_toolkit.mcp.curated.bookkeeping.document import (
    bookkeeping_document_action,
    bookkeeping_document_delete,
)
from nocfo_toolkit.mcp.curated.invoicing.purchase_invoice import (
    invoicing_purchase_invoice_delete,
    invoicing_purchase_invoice_update,
)
from nocfo_toolkit.mcp.curated.invoicing.sales_invoice import (
    invoicing_sales_invoice_action,
    invoicing_sales_invoice_send,
    invoicing_sales_invoice_update,
)
from nocfo_toolkit.mcp.curated.bookkeeping.tag_file import (
    bookkeeping_document_tags_update,
    bookkeeping_tag_create,
)
from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    AccountActionsInput,
    AccountNumbersInput,
    AccountUpdatesInput,
    DocumentActionsInput,
    DocumentTagsBatchInput,
    InvoiceUpdatesInput,
    PayloadsInput,
    PurchaseInvoiceTargetsInput,
    SalesInvoiceActionsInput,
    SalesInvoiceSendsInput,
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


def test_account_update_applies_per_target_payloads() -> None:
    # Heterogeneous: each account gets its OWN fields in one confirmed call.
    calls: list = []
    params = AccountUpdatesInput(
        business="demo",
        updates=[
            {"account_number": 1910, "payload": {"description": "Desc A"}},
            {"account_number": 2000, "payload": {"description": "Desc B"}},
        ],
    )
    result = _run_account_tool(bookkeeping_account_update, params, calls)

    assert result["total"] == 2
    assert result["succeeded"] == 2
    assert result["failed"] == 0
    patched = [c for c in calls if c[0] == "PATCH"]
    # account_id is number*10 in the stub; each PATCH carries its own payload.
    bodies = {path: body for _method, path, body in patched}
    assert bodies["/v1/business/demo/account/19100/"] == {"description": "Desc A"}
    assert bodies["/v1/business/demo/account/20000/"] == {"description": "Desc B"}


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


def test_purchase_invoice_targets_require_exactly_one_selector() -> None:
    PurchaseInvoiceTargetsInput(business="demo", invoice_numbers=[1])
    PurchaseInvoiceTargetsInput(business="demo", tool_handles=["h"])
    with pytest.raises(ValueError):
        PurchaseInvoiceTargetsInput(business="demo")
    with pytest.raises(ValueError):
        PurchaseInvoiceTargetsInput(
            business="demo", invoice_numbers=[1], tool_handles=["h"]
        )


def test_purchase_invoice_delete_accepts_tool_handle_selector() -> None:
    calls: list[tuple[str, str]] = []

    async def _request(method, path, *, business_slug=None, **_kwargs):
        calls.append((method, path))
        return None

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = PurchaseInvoiceTargetsInput(
        business="demo",
        tool_handles=encode_tool_handle("invoicing_purchase_invoice", 8),
    )
    with (
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.purchase_invoice.business_slug", _slug
        ),
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.purchase_invoice.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(invoicing_purchase_invoice_delete(params))

    assert result["succeeded"] == 1
    assert result["results"][0]["result"]["id"] == 8
    assert calls == [("DELETE", "/v1/invoicing/demo/purchase_invoice/8/")]


def test_purchase_invoice_update_accepts_tool_handle_selector() -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        calls.append((method, path, json_body))
        return {"id": 8, "invoice_number": "PI-8"}

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = InvoiceUpdatesInput(
        business="demo",
        updates=[
            {
                "tool_handle": encode_tool_handle("invoicing_purchase_invoice", 8),
                "payload": {"reference": "updated"},
            }
        ],
    )
    with (
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.purchase_invoice.business_slug", _slug
        ),
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.purchase_invoice.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(invoicing_purchase_invoice_update(params))

    assert result["succeeded"] == 1
    assert calls == [
        ("PATCH", "/v1/invoicing/demo/purchase_invoice/8/", {"reference": "updated"})
    ]


def test_purchase_invoice_update_applies_per_target_payloads() -> None:
    # Heterogeneous: two invoices, two different payloads, one call.
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        calls.append((method, path, json_body))
        return {"id": int(path.rstrip("/").split("/")[-1])}

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = InvoiceUpdatesInput(
        business="demo",
        updates=[
            {
                "tool_handle": encode_tool_handle("invoicing_purchase_invoice", 8),
                "payload": {"reference": "A"},
            },
            {
                "tool_handle": encode_tool_handle("invoicing_purchase_invoice", 9),
                "payload": {"reference": "B"},
            },
        ],
    )
    with (
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.purchase_invoice.business_slug", _slug
        ),
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.purchase_invoice.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(invoicing_purchase_invoice_update(params))

    assert result["succeeded"] == 2
    bodies = {path: body for _method, path, body in calls if _method == "PATCH"}
    assert bodies["/v1/invoicing/demo/purchase_invoice/8/"] == {"reference": "A"}
    assert bodies["/v1/invoicing/demo/purchase_invoice/9/"] == {"reference": "B"}


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


def test_account_action_applies_per_target_actions() -> None:
    calls: list[tuple[str, str]] = []

    async def _resolve_id(
        list_path, *, lookup_field, lookup_value, business_slug, search_param=None
    ):
        return int(lookup_value) * 10

    async def _request(method, path, *, business_slug=None, **_kwargs):
        calls.append((method, path))
        return None

    client = SimpleNamespace(resolve_id=_resolve_id, request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = AccountActionsInput.model_validate(
        {
            "business": "demo",
            "actions": [
                {"account_number": 1910, "action": "hide"},
                {"account_number": 2000, "action": "show"},
            ],
        }
    )
    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.account.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.account.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(bookkeeping_account_action(params))

    assert result["succeeded"] == 2
    assert ("POST", "/v1/business/demo/account/19100/hide/") in calls
    assert ("POST", "/v1/business/demo/account/20000/show/") in calls


def test_document_action_applies_per_target_actions() -> None:
    calls: list[tuple[str, str]] = []

    async def _request(method, path, *, business_slug=None, **_kwargs):
        calls.append((method, path))
        document_id = int(path.split("/document/")[1].split("/")[0])
        return {"id": document_id, "number": f"BK-{document_id}"}

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = DocumentActionsInput.model_validate(
        {
            "business": "demo",
            "actions": [
                {
                    "tool_handle": encode_tool_handle("bookkeeping_document", 5),
                    "action": "lock",
                },
                {
                    "tool_handle": encode_tool_handle("bookkeeping_document", 6),
                    "action": "unlock",
                },
            ],
        }
    )
    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.document.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(bookkeeping_document_action(params))

    assert result["succeeded"] == 2
    assert ("POST", "/v1/business/demo/document/5/action/lock/") in calls
    assert ("POST", "/v1/business/demo/document/6/action/unlock/") in calls


def test_sales_invoice_action_applies_per_target_actions() -> None:
    calls: list[tuple[str, str]] = []

    async def _resolve_id(
        list_path, *, lookup_field, lookup_value, business_slug, search_param=None
    ):
        return int(lookup_value)

    async def _request(method, path, *, business_slug=None, **_kwargs):
        calls.append((method, path))
        return {"id": 1, "status": "x"}

    client = SimpleNamespace(resolve_id=_resolve_id, request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = SalesInvoiceActionsInput.model_validate(
        {
            "business": "demo",
            "actions": [
                {"invoice_number": 101, "action": "mark_paid"},
                {"invoice_number": 102, "action": "mark_credit_loss"},
            ],
        }
    )
    with (
        patch("nocfo_toolkit.mcp.curated.invoicing.sales_invoice.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(invoicing_sales_invoice_action(params))

    assert result["succeeded"] == 2
    assert ("POST", "/v1/invoicing/demo/invoice/101/actions/paid/") in calls
    assert ("POST", "/v1/invoicing/demo/invoice/102/actions/credit_loss/") in calls


def test_sales_invoice_send_applies_per_target_delivery() -> None:
    calls: list[tuple[str, str, dict | None]] = []

    async def _resolve_id(
        list_path, *, lookup_field, lookup_value, business_slug, search_param=None
    ):
        return int(lookup_value)

    async def _request(method, path, *, json_body=None, business_slug=None, **_kwargs):
        calls.append((method, path, json_body))
        return {"id": 1}

    client = SimpleNamespace(resolve_id=_resolve_id, request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = SalesInvoiceSendsInput.model_validate(
        {
            "business": "demo",
            "sends": [
                {
                    "invoice_number": 101,
                    "delivery_method": "EMAIL",
                    "email_subject": "Invoice 101",
                    "email_content": "Hi",
                },
                {"invoice_number": 102, "delivery_method": "EINVOICE"},
            ],
        }
    )
    with (
        patch("nocfo_toolkit.mcp.curated.invoicing.sales_invoice.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(invoicing_sales_invoice_send(params))

    assert result["succeeded"] == 2
    bodies = {path: body for _method, path, body in calls}
    # Email delivery nests subject/content under data; e-invoice omits data.
    assert bodies["/v1/invoicing/demo/invoice/101/send/"] == {
        "delivery_method": "EMAIL",
        "data": {"email_subject": "Invoice 101", "email_content": "Hi"},
    }
    assert bodies["/v1/invoicing/demo/invoice/102/send/"] == {
        "delivery_method": "EINVOICE"
    }


def test_send_requires_email_subject_for_email_delivery() -> None:
    with pytest.raises(ValueError):
        SalesInvoiceSendsInput.model_validate(
            {
                "business": "demo",
                "sends": [{"invoice_number": 1, "delivery_method": "EMAIL"}],
            }
        )
    # Non-email methods do not require an email subject.
    SalesInvoiceSendsInput.model_validate(
        {
            "business": "demo",
            "sends": [{"invoice_number": 1, "delivery_method": "EINVOICE"}],
        }
    )


def test_account_update_maps_friendly_name_to_name_translations() -> None:
    # Backend `name` is read-only; the toolkit must write name_translations so a
    # plain "rename" actually applies instead of silently no-opping.
    calls: list = []
    params = AccountUpdatesInput(
        business="demo",
        updates=[{"account_number": 1910, "payload": {"name": "Bank account"}}],
    )
    result = _run_account_tool(bookkeeping_account_update, params, calls)

    assert result["succeeded"] == 1
    body = [body for method, _path, body in calls if method == "PATCH"][0]
    assert "name" not in body
    assert body["name_translations"] == [
        {"key": "fi", "value": "Bank account"},
        {"key": "sv", "value": "Bank account"},
        {"key": "en", "value": "Bank account"},
        {"key": "de", "value": "Bank account"},
    ]


def test_sales_invoice_update_rejects_read_only_due_date() -> None:
    async def _request(*_a, **_k):
        raise AssertionError("no API call expected when due_date is rejected")

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    params = InvoiceUpdatesInput.model_validate(
        {
            "business": "demo",
            "updates": [{"invoice_number": 101, "payload": {"due_date": "2026-01-01"}}],
        }
    )
    with (
        patch("nocfo_toolkit.mcp.curated.invoicing.sales_invoice.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(invoicing_sales_invoice_update(params))

    # Read-only due_date is surfaced as a clear per-item failure, not a silent no-op.
    assert result["failed"] == 1
    assert result["results"][0]["error"]["error_type"] == "invalid_request"
