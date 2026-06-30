"""Batch (mass) target input models for sales invoice MCP tools."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.batch import as_list
from nocfo_toolkit.mcp.curated.schema.common import (
    BusinessContextInput,
    DeliveryMethod,
    SalesInvoiceAction,
    StrictModel,
    enum_or_str,
)

_EMAIL_DELIVERY_METHODS = {"EMAIL", "EMAIL_XRECHNUNG"}


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


class _SalesInvoiceSelector(StrictModel):
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    tool_handle: str | None = Field(
        default=None,
        description="invoicing_sales_invoices_list.items[].tool_handle value.",
    )

    @model_validator(mode="after")
    def validate_single_selector(self) -> "_SalesInvoiceSelector":
        if (self.invoice_number is None) == (self.tool_handle is None):
            raise ValueError(
                "Provide exactly one of invoice_number or tool_handle per item."
            )
        return self


class SalesInvoiceActionItem(_SalesInvoiceSelector):
    action: enum_or_str(SalesInvoiceAction) = Field(
        description="Workflow action (accept/mark_paid/mark_unpaid/mark_credit_loss/disable_recurrence) for THIS invoice."
    )


class SalesInvoiceActionsInput(BusinessContextInput):
    actions: Annotated[list[SalesInvoiceActionItem], BeforeValidator(as_list)] = Field(
        description="One entry per invoice, each with its own workflow action. Different invoices can get different actions (e.g. mark one paid and another credit_loss) in a single confirmed call.",
        min_length=1,
    )


class SalesInvoiceSendItem(_SalesInvoiceSelector):
    delivery_method: enum_or_str(DeliveryMethod) = Field(
        description="How to send THIS invoice: EMAIL, EINVOICE, ELASKU, or PAPER. Check invoicing_sales_invoice_delivery_methods for what each invoice supports.",
    )
    email_subject: str | None = Field(
        default=None,
        description="Email subject. REQUIRED when delivery_method is EMAIL; ignored for other methods.",
    )
    email_content: str | None = Field(
        default=None,
        description="Optional email body, used only for EMAIL delivery.",
    )

    @model_validator(mode="after")
    def validate_email_fields(self) -> "SalesInvoiceSendItem":
        method = getattr(self.delivery_method, "value", self.delivery_method)
        if method in _EMAIL_DELIVERY_METHODS and not self.email_subject:
            raise ValueError("email_subject is required when delivery_method is EMAIL.")
        return self


class SalesInvoiceSendsInput(BusinessContextInput):
    sends: Annotated[list[SalesInvoiceSendItem], BeforeValidator(as_list)] = Field(
        description="One entry per invoice to send, each with its own optional delivery override. Different invoices can use different delivery methods in a single confirmed call. Call only after the user confirms sending.",
        min_length=1,
    )
