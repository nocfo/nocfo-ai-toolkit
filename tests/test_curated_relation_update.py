from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from nocfo_toolkit.mcp.curated.bookkeeping.relation import (
    _resolve_relation_update_payload,
)
from nocfo_toolkit.mcp.curated.schema.bookkeeping.document import (
    DocumentRelationUpdateInput,
)


def test_relation_update_payload_rejects_non_mutable_description_field() -> None:
    with pytest.raises(ValidationError):
        DocumentRelationUpdateInput.model_validate(
            {
                "business": "demo",
                "document_number": "42",
                "relation_id": 7,
                "payload": {"description": "not supported"},
            }
        )


def test_relation_update_payload_maps_related_document_number() -> None:
    async def _run() -> None:
        with patch(
            "nocfo_toolkit.mcp.curated.bookkeeping.relation.document_by_number",
            return_value={"id": 99},
        ):
            payload = await _resolve_relation_update_payload(
                "demo",
                {"related_document_number": "DOC-99", "role": "ACCRUAL"},
            )
        assert payload == {"related_document": 99, "role": "ACCRUAL"}

    asyncio.run(_run())


def test_relation_update_payload_requires_mutable_fields() -> None:
    async def _run() -> None:
        with pytest.raises(ToolError) as exc_info:
            await _resolve_relation_update_payload("demo", {})
        payload = json.loads(str(exc_info.value))
        assert payload["error_type"] == "invalid_request"

    asyncio.run(_run())
