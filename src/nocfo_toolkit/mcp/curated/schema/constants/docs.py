"""Constants and docs schemas."""

from __future__ import annotations

from pydantic import Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    BusinessContextInput,
    ConstantsKind,
    DocsKind,
    StrictModel,
    enum_or_str,
)


class VatRatesInput(BusinessContextInput):
    date_at: str = Field(
        description="Date whose effective VAT rates should be returned. Format: YYYY-MM-DD."
    )


class ConstantsRetrieveInput(BusinessContextInput):
    kind: enum_or_str(ConstantsKind) = Field(
        description="Which constants payload to retrieve."
    )
    date_at: str | None = Field(
        default=None,
        description="Required when kind is vat_rates; ignored for vat_codes. Format: YYYY-MM-DD.",
    )

    @model_validator(mode="after")
    def validate_constants_kind(self) -> "ConstantsRetrieveInput":
        if self.kind == ConstantsKind.vat_rates and not self.date_at:
            raise ValueError("date_at is required when kind=vat_rates")
        return self


class DocsRetrieveInput(StrictModel):
    kind: enum_or_str(DocsKind) = Field(
        description="Which guidance document to retrieve."
    )
