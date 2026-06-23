"""Batch (mass) target input models for sales invoice MCP tools."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.batch import as_list
from nocfo_toolkit.mcp.curated.schema.common import (
    BusinessContextInput,
    SalesInvoiceAction,
    enum_or_str,
)


class SalesInvoiceTargetsInput(BusinessContextInput):
    invoice_numbers: Annotated[
        list[int | str] | None, BeforeValidator(as_list)
    ] = Field(
        default=None,
        description="One or more invoice numbers visible to the user. Provide ALL targets here, or use tool_handles (not both).",
    )
    tool_handles: Annotated[list[str] | None, BeforeValidator(as_list)] = Field(
        default=None,
        description="One or more invoicing_sales_invoices_list.items[].tool_handle values. Provide ALL targets here, or use invoice_numbers (not both).",
    )

    @model_validator(mode="after")
    def validate_selector(self) -> "SalesInvoiceTargetsInput":
        has_numbers = bool(self.invoice_numbers)
        has_handles = bool(self.tool_handles)
        if has_numbers == has_handles:
            raise ValueError("Provide exactly one of invoice_numbers or tool_handles.")
        return self


class SalesInvoiceTargetsPayloadInput(SalesInvoiceTargetsInput):
    payload: dict[str, Any] = Field(
        description="Fields to update, applied identically to every target invoice."
    )


class SalesInvoiceTargetsActionInput(SalesInvoiceTargetsInput):
    action: enum_or_str(SalesInvoiceAction) = Field(
        description="Workflow action to run on every target invoice."
    )
