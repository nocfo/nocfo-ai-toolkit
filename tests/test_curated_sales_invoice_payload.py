from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

from nocfo_toolkit.mcp.curated.invoicing.sales_invoice import (
    invoicing_sales_invoice_action,
    invoicing_sales_invoice_update,
    invoicing_sales_invoice_delete,
    resolve_sales_invoice_payload,
)
from nocfo_toolkit.mcp.curated.schema.invoicing.product import ProductSummary
from nocfo_toolkit.mcp.curated.schema.invoicing.sales_invoice import (
    SalesInvoiceActionInput,
    SalesInvoiceLookupInput,
    SalesInvoicePayloadInput,
    SalesInvoiceSummary,
)
from unittest.mock import patch


def _contact_handle(contact_id: int) -> str:
    raw = json.dumps({"resource": "invoicing_contact", "id": contact_id}).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii")


def test_resolve_sales_invoice_payload_maps_receiver_id_to_receiver() -> None:
    async def _run() -> None:
        client = SimpleNamespace(resolve_id=None)
        ctx = SimpleNamespace(client=client)
        payload = {"receiver_id": 55, "rows": [{"product_id": 7}]}
        body = await resolve_sales_invoice_payload(ctx, "demo", payload)
        assert body["receiver"] == 55
        assert "receiver_id" not in body
        assert body["rows"][0]["product"] == 7
        assert "product_id" not in body["rows"][0]

    asyncio.run(_run())


def test_resolve_sales_invoice_payload_accepts_contact_tool_handle() -> None:
    async def _run() -> None:
        client = SimpleNamespace(resolve_id=None)
        ctx = SimpleNamespace(client=client)
        payload = {"receiver": {"tool_handle": _contact_handle(99)}}
        body = await resolve_sales_invoice_payload(ctx, "demo", payload)
        assert body["receiver"] == 99

    asyncio.run(_run())


def test_resolve_sales_invoice_payload_resolves_contact_name() -> None:
    captured: dict[str, object] = {}

    async def _resolve_id(
        list_path: str,
        *,
        lookup_field: str,
        lookup_value: object,
        business_slug: str,
        search_param: str | None = None,
    ) -> int:
        captured["list_path"] = list_path
        captured["lookup_field"] = lookup_field
        captured["lookup_value"] = lookup_value
        captured["business_slug"] = business_slug
        captured["search_param"] = search_param
        return 321

    async def _run() -> None:
        client = SimpleNamespace(resolve_id=_resolve_id)
        ctx = SimpleNamespace(client=client)
        payload = {"contact": "Receiver Oy"}
        body = await resolve_sales_invoice_payload(ctx, "demo", payload)
        assert body["receiver"] == 321
        assert "contact" not in body

    asyncio.run(_run())
    assert captured == {
        "list_path": "/v1/business/demo/contacts/",
        "lookup_field": "name",
        "lookup_value": "Receiver Oy",
        "business_slug": "demo",
        "search_param": "search",
    }


def test_resolve_sales_invoice_payload_patch_omits_missing_receiver() -> None:
    async def _run() -> None:
        client = SimpleNamespace(resolve_id=None)
        ctx = SimpleNamespace(client=client)
        payload = {"description": "Only description change"}
        body = await resolve_sales_invoice_payload(ctx, "demo", payload)
        assert body["description"] == "Only description change"
        assert "receiver" not in body

    asyncio.run(_run())


def test_sales_invoice_delete_accepts_tool_handle_selector() -> None:
    calls: list[tuple[str, str]] = []

    class _FakeClient:
        async def request(self, method: str, path: str, **_: object) -> None:
            calls.append((method, path))
            return None

    async def _run() -> None:
        params = SalesInvoiceLookupInput.model_validate(
            {
                "business": "demo",
                "tool_handle": base64.urlsafe_b64encode(
                    json.dumps(
                        {"resource": "invoicing_sales_invoice", "id": 77}
                    ).encode("utf-8")
                ).decode("ascii"),
            }
        )
        with (
            patch(
                "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.business_slug",
                return_value="demo",
            ),
            patch(
                "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.get_client",
                return_value=_FakeClient(),
            ),
        ):
            result = await invoicing_sales_invoice_delete(params)
        assert result["id"] == 77

    asyncio.run(_run())
    assert calls == [("DELETE", "/v1/invoicing/demo/invoice/77/")]


def test_sales_invoice_update_accepts_tool_handle_selector() -> None:
    calls: list[tuple[str, str]] = []

    class _FakeClient:
        async def request(
            self, method: str, path: str, **_: object
        ) -> dict[str, object]:
            calls.append((method, path))
            return {"id": 77, "status": "DRAFT"}

    async def _run() -> None:
        params = SalesInvoicePayloadInput.model_validate(
            {
                "business": "demo",
                "tool_handle": base64.urlsafe_b64encode(
                    json.dumps(
                        {"resource": "invoicing_sales_invoice", "id": 77}
                    ).encode("utf-8")
                ).decode("ascii"),
                "payload": {"description": "updated"},
            }
        )
        with (
            patch(
                "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.business_slug",
                return_value="demo",
            ),
            patch(
                "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.get_client",
                return_value=_FakeClient(),
            ),
        ):
            await invoicing_sales_invoice_update(params)

    asyncio.run(_run())
    assert calls == [("PATCH", "/v1/invoicing/demo/invoice/77/")]


def test_sales_invoice_action_accepts_tool_handle_selector() -> None:
    calls: list[tuple[str, str]] = []

    class _FakeClient:
        async def request(
            self, method: str, path: str, **_: object
        ) -> dict[str, object]:
            calls.append((method, path))
            return {"id": 77, "status": "ACCEPTED"}

    async def _run() -> None:
        params = SalesInvoiceActionInput.model_validate(
            {
                "business": "demo",
                "tool_handle": base64.urlsafe_b64encode(
                    json.dumps(
                        {"resource": "invoicing_sales_invoice", "id": 77}
                    ).encode("utf-8")
                ).decode("ascii"),
                "action": "accept",
            }
        )
        with (
            patch(
                "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.business_slug",
                return_value="demo",
            ),
            patch(
                "nocfo_toolkit.mcp.curated.invoicing.sales_invoice.get_client",
                return_value=_FakeClient(),
            ),
        ):
            await invoicing_sales_invoice_action(params)

    asyncio.run(_run())
    assert calls == [
        ("POST", "/v1/invoicing/demo/invoice/77/actions/accept/"),
    ]


def test_sales_invoice_summary_prefers_tool_handle_hint_for_draft_without_number() -> (
    None
):
    summary = SalesInvoiceSummary.model_validate({"id": 77, "status": "DRAFT"})
    assert summary.next_action == "accept"
    assert summary.next_action_hint is not None
    assert "tool_handle" in summary.next_action_hint


def test_product_summary_exposes_vat_inclusive_toggle_fields() -> None:
    fields = ProductSummary.model_fields
    assert "is_vat_inclusive" in fields
    assert "vat_exclusive_amount" in fields
    assert "vat_inclusive_amount" in fields
    assert "vat_amount" in fields
