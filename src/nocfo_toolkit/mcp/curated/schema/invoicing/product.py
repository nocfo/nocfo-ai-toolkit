"""Invoicing product schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import AgentModel, tool_handle


class ProductListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to invoicing_product_retrieve.",
    )
    id: int | None = Field(
        default=None, description="Product ID for exact follow-up calls."
    )
    code: str | None = Field(
        default=None, description="Product code for deterministic lookup."
    )
    name: str | None = Field(default=None, description="Display name.")
    unit: str | None = Field(
        default=None, description="Product unit shown on invoice rows."
    )

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "tool_handle" not in data and isinstance(data.get("id"), int):
            data["tool_handle"] = tool_handle("invoicing_product", data["id"])
        return data


class ProductSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from invoicing_products_list.items[].tool_handle and pass it unchanged to invoicing_product_retrieve.",
    )
    id: int | None = Field(
        default=None,
        description="Product ID. Use invoicing_product_retrieve to expand this ID.",
    )
    code: str | None = Field(
        default=None,
        description="Product code. Use this for deterministic product lookup.",
    )
    name: str | None = Field(default=None, description="Display name.")
    unit: str | None = Field(
        default=None, description="Product unit shown on invoice rows."
    )
    amount: Any | None = Field(
        default=None,
        description="Product unit price. Interpretation depends on is_vat_inclusive: true means amount includes VAT, false means amount excludes VAT.",
    )
    is_vat_inclusive: bool | None = Field(
        default=None,
        description="Toggle for amount interpretation: true = VAT-inclusive unit price, false = VAT-exclusive unit price.",
    )
    vat_exclusive_amount: Any | None = Field(
        default=None,
        description="Derived unit price excluding VAT.",
    )
    vat_inclusive_amount: Any | None = Field(
        default=None,
        description="Derived unit price including VAT.",
    )
    vat_amount: Any | None = Field(
        default=None, description="Derived VAT amount per unit."
    )
    vat_rate: Any | None = Field(
        default=None,
        description="VAT rate associated with this row or entry. To see valid/effective VAT rates, call constants_retrieve with kind=vat_rates (date_at required).",
    )
    vat_code: Any | None = Field(
        default=None,
        description="VAT code associated with this row or entry. To see valid VAT codes, call constants_retrieve with kind=vat_codes.",
    )
