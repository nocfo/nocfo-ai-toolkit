from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from nocfo_toolkit.mcp.curated.bookkeeping.attachment import (
    bookkeeping_document_suggested_attachments_list,
)
from nocfo_toolkit.mcp.curated.schemas import DocumentRetrieveInput
from nocfo_toolkit.mcp.curated.utils import encode_tool_handle


def test_suggested_attachments_lists_candidates_with_detail() -> None:
    candidates = [
        {
            "id": 9,
            "name": "lunch.jpg",
            "type": "image/jpeg",
            "analysis_status": "complete",
            "analysis_badges": {"primary_date": "2026-01-05", "total_amount": "42.00"},
        }
    ]

    async def _request(method, path, *, business_slug=None, **_k):
        assert path.endswith("/suggest_attachments/")
        return candidates

    client = SimpleNamespace(request=_request)

    async def _slug(_: str) -> str:
        return "demo"

    with (
        patch("nocfo_toolkit.mcp.curated.bookkeeping.attachment.business_slug", _slug),
        patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.attachment.get_client",
            return_value=client,
        ),
    ):
        result = asyncio.run(
            bookkeeping_document_suggested_attachments_list(
                DocumentRetrieveInput(
                    business="demo",
                    tool_handle=encode_tool_handle("bookkeeping_document", 5),
                )
            )
        )
    # Candidates carry triage detail (type + detected date/total) for the decision.
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == 9
    assert result["items"][0]["content_type"] == "image/jpeg"
    assert result["items"][0]["analysis_badges"]["total_amount"] == "42.00"
