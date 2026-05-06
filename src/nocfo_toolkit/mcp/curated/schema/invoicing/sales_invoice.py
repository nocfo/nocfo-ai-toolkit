"""Invoicing sales invoice schemas."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    DeliveryMethod,
    AgentModel,
    BusinessContextInput,
    BusinessPaginationInput,
    SalesInvoiceAction,
    SalesInvoiceStatus,
    enum_or_str,
    tool_handle,
)


def _derive_invoice_next_action(
    *, status_raw: str | None, is_sendable: bool | None, last_delivery_at: str | None
) -> tuple[str | None, str | None]:
    status = str(status_raw).strip().upper() if status_raw is not None else ""
    can_send = bool(is_sendable)

    if status == "DRAFT":
        return (
            "accept",
            "Invoice is in DRAFT status. Next step: call invoicing_sales_invoice_action with action=accept.",
        )

    if can_send and not last_delivery_at:
        return (
            "send",
            "Invoice is accepted and ready to send. Next step: call invoicing_sales_invoice_send after user confirmation.",
        )

    return None, None


class InvoiceLookupInput(BusinessContextInput):
    invoice_number: int | str = Field(description="Invoice number visible to the user.")


class InvoiceRetrieveInput(BusinessContextInput):
    tool_handle: str = Field(
        description="Value copied from invoicing_sales_invoices_list.items[].tool_handle or invoicing_purchase_invoices_list.items[].tool_handle. Pass it unchanged to the matching invoice retrieve tool; do not use invoice numbers or database IDs here."
    )


class InvoicePayloadInput(InvoiceLookupInput):
    payload: dict[str, Any] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class SalesInvoiceRowPayload(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    product: Any | None = Field(
        default=None,
        validation_alias=AliasChoices("product", "product_id"),
    )


class SalesInvoiceMutationPayload(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    receiver: Any | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "receiver", "receiver_id", "contact_id", "contact"
        ),
    )
    rows: list[Any] | None = Field(
        default=None,
        description="Invoice row payloads.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_receiver_reference(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        receiver = data.get("receiver")
        if isinstance(receiver, dict):
            for key in ("id", "tool_handle", "name"):
                if key in receiver:
                    data["receiver"] = receiver[key]
                    break
        return data

    @model_validator(mode="before")
    @classmethod
    def normalize_rows(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        rows = data.get("rows")
        if not isinstance(rows, list):
            return data
        data["rows"] = [
            SalesInvoiceRowPayload.model_validate(row).model_dump(
                mode="json",
                by_alias=True,
            )
            if isinstance(row, dict)
            else row
            for row in rows
        ]
        return data


class SalesInvoicesListInput(BusinessPaginationInput):
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    status: enum_or_str(SalesInvoiceStatus) | None = Field(
        default=None,
        description="Filter by invoice status. Allowed values: DRAFT, ACCEPTED, PAID, CREDIT_LOSS.",
    )
    invoicing_date_from: str | None = Field(
        default=None,
        description="Include invoices dated on or after this date. Format: YYYY-MM-DD.",
    )
    invoicing_date_to: str | None = Field(
        default=None,
        description="Include invoices dated on or before this date. Format: YYYY-MM-DD.",
    )
    due_date_from: str | None = Field(
        default=None,
        description="Include invoices due on or after this date. Format: YYYY-MM-DD.",
    )
    due_date_to: str | None = Field(
        default=None,
        description="Include invoices due on or before this date. Format: YYYY-MM-DD.",
    )

    def query_params(self) -> dict[str, Any]:
        params = {
            "invoice_number": self.invoice_number,
            "search": self.query,
            "status": self.status.value if self.status is not None else None,
            "invoicing_date_gte": self.invoicing_date_from,
            "invoicing_date_lte": self.invoicing_date_to,
            "due_date_gte": self.due_date_from,
            "due_date_lte": self.due_date_to,
        }
        return {key: value for key, value in params.items() if value is not None}


class SalesInvoiceActionInput(InvoiceLookupInput):
    action: enum_or_str(SalesInvoiceAction) = Field(
        description="Action to run on the selected resource."
    )


class SalesInvoiceSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from invoicing_sales_invoices_list.items[].tool_handle and pass it unchanged to invoicing_sales_invoice_retrieve.",
    )
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    status: enum_or_str(SalesInvoiceStatus) | None = Field(
        default=None,
        description="Invoice status. Allowed values: DRAFT, ACCEPTED, PAID, CREDIT_LOSS.",
    )
    receiver_id: int | str | None = Field(
        default=None,
        validation_alias=AliasChoices("receiver_id", "receiver"),
        description="Receiver contact ID. Use invoicing_contact_retrieve to expand this ID when needed.",
    )
    receiver_info: Any | None = Field(
        default=None, description="Compact receiver information for the invoice."
    )
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    invoicing_date: str | None = Field(
        default=None, description="Invoice date. Format: YYYY-MM-DD."
    )
    due_date: str | None = Field(
        default=None, description="Invoice due date. Format: YYYY-MM-DD."
    )
    reference: str | None = Field(
        default=None, description="Invoice or payment reference."
    )
    delivery_method: enum_or_str(DeliveryMethod) | None = Field(
        default=None,
        description="Selected or current invoice delivery method. Known values include EMAIL, EINVOICE, ELASKU, and PAPER.",
    )
    last_delivery_at: str | None = Field(
        default=None, description="Timestamp of the latest invoice delivery attempt."
    )
    settlement_date: str | None = Field(
        default=None,
        description="Date when the invoice was settled. Format: YYYY-MM-DD.",
    )
    total_vat_amount: Any | None = Field(
        default=None, description="Total VAT amount for the invoice."
    )
    total_amount: Any | None = Field(default=None, description="Total invoice amount.")
    is_editable: bool | None = Field(
        default=None, description="Whether the invoice can currently be edited."
    )
    is_sendable: bool | None = Field(
        default=None, description="Whether the invoice can currently be sent."
    )
    is_past_due: bool | None = Field(
        default=None, description="Whether the due date has passed."
    )
    next_action: str | None = Field(
        default=None,
        description="Suggested next workflow action for this invoice, for example accept or send.",
    )
    next_action_hint: str | None = Field(
        default=None,
        description="Short guidance explaining the suggested next action and matching tool call.",
    )
    rows: Any | None = Field(
        default=None, description="Invoice rows included on the invoice."
    )
    external_status_messages: Any | None = Field(
        default=None, description="Delivery and status messages for this invoice."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_invoice_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        receiver = data.get("receiver")
        if (
            isinstance(receiver, dict)
            and "id" in receiver
            and "receiver_id" not in data
        ):
            data["receiver_id"] = receiver["id"]
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("invoicing_sales_invoice", raw_id)
        return data

    @model_validator(mode="after")
    def apply_workflow_hint(self) -> "SalesInvoiceSummary":
        if self.next_action is None or self.next_action_hint is None:
            next_action, next_action_hint = _derive_invoice_next_action(
                status_raw=self.status,
                is_sendable=self.is_sendable,
                last_delivery_at=self.last_delivery_at,
            )
            if self.next_action is None:
                self.next_action = next_action
            if self.next_action_hint is None:
                self.next_action_hint = next_action_hint
        return self


class SalesInvoiceListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to invoicing_sales_invoice_retrieve. Do not edit or derive it from invoice numbers.",
    )
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    status: enum_or_str(SalesInvoiceStatus) | None = Field(
        default=None,
        description="Current invoice status. Allowed values: DRAFT, ACCEPTED, PAID, CREDIT_LOSS.",
    )
    receiver_id: int | str | None = Field(
        default=None,
        validation_alias=AliasChoices("receiver_id", "receiver"),
        description="Receiver contact ID for follow-up lookups.",
    )
    invoicing_date: str | None = Field(
        default=None, description="Invoice date. Format: YYYY-MM-DD."
    )
    due_date: str | None = Field(
        default=None, description="Invoice due date. Format: YYYY-MM-DD."
    )
    reference: str | None = Field(
        default=None, description="Invoice or payment reference."
    )
    total_amount: Any | None = Field(default=None, description="Total invoice amount.")
    is_editable: bool | None = Field(
        default=None, description="Whether the invoice can be edited."
    )
    is_sendable: bool | None = Field(
        default=None, description="Whether the invoice can be sent."
    )
    is_past_due: bool | None = Field(
        default=None, description="Whether the due date has passed."
    )
    next_action: str | None = Field(
        default=None,
        description="Suggested next workflow action for this invoice, for example accept or send.",
    )
    next_action_hint: str | None = Field(
        default=None,
        description="Short guidance explaining the suggested next action and matching tool call.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_list_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        receiver = data.get("receiver")
        if (
            isinstance(receiver, dict)
            and "id" in receiver
            and "receiver_id" not in data
        ):
            data["receiver_id"] = receiver["id"]
        next_action, next_action_hint = _derive_invoice_next_action(
            status_raw=data.get("status"),
            is_sendable=data.get("is_sendable"),
            last_delivery_at=data.get("last_delivery_at"),
        )
        if "next_action" not in data:
            data["next_action"] = next_action
        if "next_action_hint" not in data:
            data["next_action_hint"] = next_action_hint
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("invoicing_sales_invoice", raw_id)
        return data
