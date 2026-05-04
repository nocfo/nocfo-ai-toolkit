from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from nocfo_toolkit.mcp.curated.bookkeeping.document import (
    resolve_blueprint,
    resolve_document_payload,
)
from nocfo_toolkit.mcp.curated.schema.bookkeeping.document import (
    DocumentMutationPayload,
)


def test_resolve_blueprint_maps_account_numbers_to_ids() -> None:
    calls: list[object] = []

    async def _resolve_id(
        list_path: str,
        *,
        lookup_field: str,
        lookup_value: object,
        business_slug: str,
        search_param: str | None = None,
    ) -> int:
        calls.append(lookup_value)
        mapping = {1910: 10, 3000: 30, 4000: 40}
        return mapping[int(lookup_value)]

    async def _run() -> None:
        client = SimpleNamespace(resolve_id=_resolve_id)
        blueprint = {
            "debet_account_number": 1910,
            "credit_account_id": 20,
            "debet_entries": [{"account_number": "3000", "amount": "100.00"}],
            "credit_entries": [{"account_id": "40", "amount": "100.00"}],
        }
        with patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ):
            body = await resolve_blueprint("demo", blueprint)

        assert body["debet_account_id"] == 10
        assert body["credit_account_id"] == 20
        assert "debet_account_number" not in body
        assert "credit_account_number" not in body
        assert body["debet_entries"][0]["account_id"] == 30
        assert "account_number" not in body["debet_entries"][0]
        assert body["credit_entries"][0]["account_id"] == 40
        assert "account_number" not in body["credit_entries"][0]

    asyncio.run(_run())
    assert calls == [1910, 3000]


def test_resolve_document_payload_patch_omits_missing_and_keeps_explicit_none() -> None:
    async def _resolve_id(
        list_path: str,
        *,
        lookup_field: str,
        lookup_value: object,
        business_slug: str,
        search_param: str | None = None,
    ) -> int:
        raise AssertionError("resolve_id should not be called in this test")

    async def _run() -> None:
        client = SimpleNamespace(resolve_id=_resolve_id)
        omitted_payload = DocumentMutationPayload.model_validate({})
        with patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ):
            omitted_body = await resolve_document_payload(
                "demo",
                omitted_payload,
                is_patch=True,
            )
        assert "contact_id" not in omitted_body

        explicit_null_payload = DocumentMutationPayload.model_validate(
            {"contact_id": None}
        )
        with patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ):
            explicit_null_body = await resolve_document_payload(
                "demo",
                explicit_null_payload,
                is_patch=True,
            )
        assert "contact_id" in explicit_null_body
        assert explicit_null_body["contact_id"] is None

    asyncio.run(_run())


def test_resolve_document_payload_uses_contact_name_field() -> None:
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
        return 77

    async def _run() -> None:
        client = SimpleNamespace(resolve_id=_resolve_id)
        payload = DocumentMutationPayload.model_validate(
            {"contact": "Receiver Oy", "blueprint": {}}
        )
        with patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ):
            body = await resolve_document_payload(
                "demo",
                payload,
                is_patch=False,
            )
        assert body["contact_id"] == 77
        assert "contact" not in body

    asyncio.run(_run())
    assert captured == {
        "list_path": "/v1/business/demo/contacts/",
        "lookup_field": "name",
        "lookup_value": "Receiver Oy",
        "business_slug": "demo",
        "search_param": "search",
    }
