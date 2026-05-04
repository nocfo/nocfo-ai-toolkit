"""Bookkeeping header schemas."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from nocfo_toolkit.mcp.curated.schema.common import (
    AccountType,
    AgentModel,
    BusinessContextInput,
    BusinessPaginationInput,
    enum_or_str,
)


class HeaderListInput(BusinessPaginationInput):
    pass


class HeaderIdInput(BusinessContextInput):
    header_id: int = Field(
        description="Account header ID. Use bookkeeping_header_retrieve to expand this ID."
    )


class HeaderPayloadInput(BusinessContextInput):
    payload: dict[str, object] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class HeaderSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from bookkeeping_headers_list.items[].tool_handle and pass it unchanged to bookkeeping_header_retrieve.",
    )
    id: int | None = Field(
        default=None,
        description="Header ID. Use bookkeeping_header_retrieve to expand this ID.",
    )
    name: str | None = Field(default=None, description="Display name.")
    type: enum_or_str(AccountType) | None = Field(
        default=None,
        description="Type/category shown for this record.",
    )
    parent_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("parent_id", "parent"),
        description="Parent header ID. Use bookkeeping_header_retrieve to expand this ID.",
    )
    parent_ids: list[int] | None = Field(
        default=None, description="Ancestor header IDs from root to parent."
    )
    level: int | None = Field(
        default=None, description="Depth level in the header hierarchy."
    )
