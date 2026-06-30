"""Bookkeeping business tag and file schemas."""

from __future__ import annotations


from typing import Annotated, Any

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field

from nocfo_toolkit.mcp.curated.schema.batch import ToolHandlesInput, as_list
from nocfo_toolkit.mcp.curated.schema.common import (
    AgentModel,
    BusinessContextInput,
    BusinessPaginationInput,
)


class TagListInput(BusinessPaginationInput):
    pass


class FileUploadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    filename: str = Field(
        validation_alias=AliasChoices("filename", "name"),
        description="File name to show for the uploaded attachment.",
    )
    file_base64: str = Field(description="File contents encoded as base64.")
    content_type: str = Field(
        default="application/octet-stream",
        description="File media type, for example application/pdf or image/png.",
    )


class FileUploadsInput(BusinessContextInput):
    files: Annotated[list[FileUploadSpec], BeforeValidator(as_list)] = Field(
        description="One or more files to upload; one entry per attachment."
    )


class DocumentTagsBatchInput(ToolHandlesInput):
    tag_names: list[str] = Field(
        description="Tag names applied identically to every target document. Tags must already exist; "
        "create missing tags first with bookkeeping_tag_create."
    )


class TagSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from bookkeeping_tags_list.items[].tool_handle and pass it unchanged to bookkeeping_tag_retrieve.",
    )
    id: int | None = Field(
        default=None,
        description="Shared business tag ID. Use bookkeeping_tag_retrieve to expand this ID.",
    )
    name: str | None = Field(default=None, description="Display name.")
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    color: str | None = Field(default=None, description="Display color for a tag.")


class FileSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from bookkeeping_files_list.items[].tool_handle and pass it unchanged to bookkeeping_file_retrieve.",
    )
    id: int | None = Field(
        default=None,
        description="File ID. Use bookkeeping_file_retrieve to expand this ID, and to attach the file to a document with bookkeeping_documents_bulk_edit (an add_attachments edit).",
    )
    name: str | None = Field(default=None, description="Display name.")
    file_name: str | None = Field(
        default=None, description="Stored file name shown for the attachment."
    )
    content_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("content_type", "type"),
        description="File media type, for example application/pdf or image/png.",
    )
    size: int | None = Field(
        default=None, description="File size in bytes when available."
    )
    analysis_status: str | None = Field(
        default=None,
        description="Status of automatic content analysis (e.g. pending, complete, failed).",
    )
    analysis_badges: Any | None = Field(
        default=None,
        description="Extracted highlights from the file's content, such as its detected date and total amount. Use these — together with the document's own date/amount/contact — to judge whether the file truly belongs on a document before attaching it.",
    )
    created_at: str | None = Field(
        default=None, description="When this record was created."
    )
    updated_at: str | None = Field(
        default=None, description="When this record was last updated."
    )


class FileDetail(FileSummary):
    """Full file detail, including recognized content for attach decisions."""

    analysis: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Recognized fields extracted from the file's content, keyed by type — e.g. "
            "ATTACHMENT_TYPE (invoice/receipt), CONTACT_NAME (merchant/issuer), TOTAL_AMOUNT, "
            "CURRENCY_CODE, INVOICE_DATE/RECEIPT_DATE, INVOICE_DUE_DATE, PAYMENT_REFERENCE. "
            "Compare these against the document's contact, date, amount, and blueprint to decide "
            "whether this file truly belongs on the document before attaching it."
        ),
    )
    analysis_results: Any | None = Field(
        default=None,
        description="Raw per-block content-analysis output when available, for deeper inspection.",
    )
