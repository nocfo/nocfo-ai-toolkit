from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace

from nocfo_toolkit.mcp.curated.invoicing.sales_invoice import (
    resolve_sales_invoice_payload,
)
from nocfo_toolkit.mcp.curated.schema.invoicing.product import ProductSummary


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


def test_product_summary_exposes_vat_inclusive_toggle_fields() -> None:
    fields = ProductSummary.model_fields
    assert "is_vat_inclusive" in fields
    assert "vat_exclusive_amount" in fields
    assert "vat_inclusive_amount" in fields
    assert "vat_amount" in fields
