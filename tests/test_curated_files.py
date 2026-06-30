from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from nocfo_toolkit.mcp.curated.bookkeeping.document import bookkeeping_document_retrieve
from nocfo_toolkit.mcp.curated.bookkeeping.tag_file import bookkeeping_file_retrieve
from nocfo_toolkit.mcp.curated.schemas import DocumentRetrieveInput, IdInput
from nocfo_toolkit.mcp.curated.utils import encode_tool_handle


def _run(coro, client):
    async def _slug(_: str) -> str:
        return "demo"

    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.tag_file.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.tag_file.get_client",
            return_value=client,
        ),
    ):
        return asyncio.run(coro())


def test_file_retrieve_surfaces_full_recognized_content() -> None:
    file_detail = {
        "id": 5,
        "name": "receipt.pdf",
        "type": "application/pdf",
        "analysis_status": "complete",
        "analysis_badges": {"primary_date": "2026-01-05", "total_amount": "120.00"},
        "analysis_results": [
            {
                "values": [
                    {"type": "ATTACHMENT_TYPE", "value": "RECEIPT"},
                    {"type": "CONTACT_NAME", "value": "Acme Oy"},
                    {"type": "TOTAL_AMOUNT", "value": 12000},
                    {"type": "RECEIPT_DATE", "value": "2026-01-05"},
                ]
            }
        ],
    }
    client = SimpleNamespace(
        request=lambda *a, **k: _async(file_detail),
    )

    def coro():
        return bookkeeping_file_retrieve(IdInput(business="demo", id=5))

    result = _run(coro, client)
    # content_type populated from the backend "type"; quick badges retained.
    assert result["content_type"] == "application/pdf"
    assert result["analysis_status"] == "complete"
    assert result["analysis_badges"]["total_amount"] == "120.00"
    # Full recognized fields are flattened so the agent can judge relevance.
    assert result["analysis"]["CONTACT_NAME"] == "Acme Oy"
    assert result["analysis"]["ATTACHMENT_TYPE"] == "RECEIPT"
    assert result["analysis"]["TOTAL_AMOUNT"] == 12000


def test_document_retrieve_exposes_attachment_ids() -> None:
    document = {
        "id": 5,
        "number": "BK-5",
        "tag_ids": [1],
        "attachment_ids": [3, 9],
        "blueprint": {},
    }

    async def _request(method, path, *, params=None, business_slug=None, **kwargs):
        if path.endswith("/entry/"):
            return {"results": []}
        return document

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.document.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.document.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            bookkeeping_document_retrieve(
                DocumentRetrieveInput(
                    business="demo",
                    tool_handle=encode_tool_handle("bookkeeping_document", 5),
                )
            )
        )
    # The normal retrieve exposes the document's attached file ids so Luca can
    # see what is attached and decide before attaching/detaching.
    assert result["attachment_ids"] == [3, 9]


async def _async(value):
    return value
