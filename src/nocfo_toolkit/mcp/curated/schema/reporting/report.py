"""Reporting and period schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    AgentModel,
    BusinessContextInput,
    StrictModel,
    tool_handle,
)


class ReportDateRangeInput(BusinessContextInput):
    date_from: str = Field(
        description="Start date for a date range, inclusive. Format: YYYY-MM-DD."
    )
    date_to: str = Field(
        description="End date for a date range, inclusive. Format: YYYY-MM-DD."
    )
    tag_names: list[str] | None = Field(
        default=None,
        description="Shared business tag names used to filter report rows and totals.",
    )


class ReportPointInTimeInput(BusinessContextInput):
    date_at: str = Field(description="Point-in-time report date. Format: YYYY-MM-DD.")
    tag_names: list[str] | None = Field(
        default=None,
        description="Shared business tag names used to filter report rows and totals.",
    )


class PeriodSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from reporting_periods_list.items[].tool_handle and pass it unchanged to reporting_accounting_period_retrieve or reporting_vat_period_retrieve.",
    )
    id: int | None = Field(
        default=None,
        description="Period ID. Use reporting_accounting_period_retrieve or reporting_vat_period_retrieve to expand this ID.",
    )
    start_date: str | None = Field(
        default=None, description="Period start date. Format: YYYY-MM-DD."
    )
    end_date: str | None = Field(
        default=None, description="Period end date. Format: YYYY-MM-DD."
    )
    is_locked: bool | None = Field(
        default=None,
        description="True when the record is locked and should not be changed before unlocking.",
    )
    is_reported: bool | None = Field(
        default=None, description="Whether the period has been reported."
    )
    period: Any | None = Field(
        default=None,
        description="Period label or VAT reporting period information.",
    )


class PeriodListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to reporting_accounting_period_retrieve or reporting_vat_period_retrieve.",
    )
    id: int | None = Field(
        default=None, description="Period ID for exact follow-up calls."
    )
    start_date: str | None = Field(
        default=None, description="Period start date. Format: YYYY-MM-DD."
    )
    end_date: str | None = Field(
        default=None, description="Period end date. Format: YYYY-MM-DD."
    )
    is_locked: bool | None = Field(
        default=None, description="Whether the period is locked."
    )
    is_reported: bool | None = Field(
        default=None, description="Whether the period is reported."
    )

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "tool_handle" not in data and isinstance(data.get("id"), int):
            data["tool_handle"] = tool_handle("reporting_period", data["id"])
        return data


class ReportResponse(StrictModel):
    report_type: str = Field(description="Report type that was generated.")
    business: str = Field(
        description="Use current by default; provide a business slug only when the user explicitly selects another business."
    )
    data: Any = Field(
        description="Report contents for the requested dates and filters."
    )
    next_action_hint: str | None = Field(
        default=None, description="Short hint for narrowing or continuing report work."
    )
