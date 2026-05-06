"""Invoicing purchase invoice schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    AgentModel,
    BusinessPaginationInput,
    tool_handle,
)


class PurchaseInvoicesListInput(BusinessPaginationInput):
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )

    def query_params(self) -> dict[str, Any]:
        params = {"invoice_number": self.invoice_number, "search": self.query}
        return {key: value for key, value in params.items() if value is not None}


class PurchaseInvoiceSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from invoicing_purchase_invoices_list.items[].tool_handle and pass it unchanged to invoicing_purchase_invoice_retrieve.",
    )
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    sender_name: str | None = Field(
        default=None, description="Purchase invoice sender name."
    )
    sender_vat: str | None = Field(
        default=None, description="Purchase invoice sender VAT identifier."
    )
    sender_bank_account: str | None = Field(
        default=None, description="Sender bank account for purchase invoice payment."
    )
    sender_bank_bic: str | None = Field(
        default=None, description="Sender bank BIC for purchase invoice payment."
    )
    receiver_vat: str | None = Field(
        default=None, description="Receiver VAT identifier."
    )
    receiver_name: str | None = Field(default=None, description="Receiver name.")
    reference: str | None = Field(
        default=None, description="Invoice or payment reference."
    )
    message: str | None = Field(
        default=None, description="Free-text purchase invoice message."
    )
    amount: Any | None = Field(
        default=None, description="Purchase invoice total amount."
    )
    currency: str | None = Field(
        default=None, description="Currency code for the amount."
    )
    invoicing_date: str | None = Field(
        default=None, description="Invoice date. Format: YYYY-MM-DD."
    )
    due_date: str | None = Field(
        default=None, description="Invoice due date. Format: YYYY-MM-DD."
    )
    is_paid: bool | None = Field(
        default=None, description="Whether the purchase invoice is marked paid."
    )
    is_past_due: bool | None = Field(
        default=None, description="Whether the due date has passed."
    )
    payment_date: str | None = Field(
        default=None, description="Payment date when known. Format: YYYY-MM-DD."
    )
    import_source: str | None = Field(
        default=None,
        description="Source through which the purchase invoice was imported.",
    )
    document_handle: str | None = Field(
        default=None,
        description="Value copied from the linked document field. Pass it unchanged to bookkeeping_document_retrieve.",
    )
    document_number: str | int | None = Field(
        default=None, description="Linked bookkeeping document number when available."
    )
    virtuaaliviivakoodi: str | None = Field(
        default=None, description="Finnish virtual barcode for payment when available."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_document_linkage(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        document = data.get("document")
        if isinstance(document, dict):
            if "document_number" not in data and document.get("number") is not None:
                data["document_number"] = document.get("number")
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handles(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("invoicing_purchase_invoice", raw_id)
        document = data.get("document")
        document_id: int | None = None
        if isinstance(document, dict) and isinstance(document.get("id"), int):
            document_id = document["id"]
        elif isinstance(document, int):
            document_id = document
        if "document_handle" not in data and isinstance(document_id, int):
            data["document_handle"] = tool_handle("bookkeeping_document", document_id)
        return data


class PurchaseInvoiceListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to invoicing_purchase_invoice_retrieve. Do not edit or derive it from invoice numbers.",
    )
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    sender_name: str | None = Field(
        default=None, description="Purchase invoice sender name."
    )
    amount: Any | None = Field(
        default=None, description="Purchase invoice total amount."
    )
    currency: str | None = Field(
        default=None, description="Currency code for the amount."
    )
    invoicing_date: str | None = Field(
        default=None, description="Invoice date. Format: YYYY-MM-DD."
    )
    due_date: str | None = Field(
        default=None, description="Invoice due date. Format: YYYY-MM-DD."
    )
    is_paid: bool | None = Field(
        default=None, description="Whether invoice is marked paid."
    )
    is_past_due: bool | None = Field(
        default=None, description="Whether due date has passed."
    )
    import_source: str | None = Field(
        default=None, description="Source through which the invoice was imported."
    )
    document_handle: str | None = Field(
        default=None,
        description="Value copied from the linked document field. Pass it unchanged to bookkeeping_document_retrieve when available.",
    )
    document_number: str | int | None = Field(
        default=None, description="Linked bookkeeping document number when available."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_document_linkage(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        document = data.get("document")
        if isinstance(document, dict):
            if "document_number" not in data and document.get("number") is not None:
                data["document_number"] = document.get("number")
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handles(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("invoicing_purchase_invoice", raw_id)
        document = data.get("document")
        document_id: int | None = None
        if isinstance(document, dict) and isinstance(document.get("id"), int):
            document_id = document["id"]
        elif isinstance(document, int):
            document_id = document
        if "document_handle" not in data and isinstance(document_id, int):
            data["document_handle"] = tool_handle("bookkeeping_document", document_id)
        return data
