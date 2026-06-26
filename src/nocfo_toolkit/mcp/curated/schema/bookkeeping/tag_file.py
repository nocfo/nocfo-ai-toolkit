"""Bookkeeping business tag and file schemas."""

from __future__ import annotations


from typing import Annotated

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
        description="File ID. Use bookkeeping_file_retrieve to expand this ID.",
    )
    name: str | None = Field(default=None, description="Display name.")
    file_name: str | None = Field(
        default=None, description="Stored file name shown for the attachment."
    )
    content_type: str | None = Field(
        default=None,
        description="File media type, for example application/pdf or image/png.",
    )
    size: int | None = Field(
        default=None, description="File size in bytes when available."
    )
    created_at: str | None = Field(
        default=None, description="When this record was created."
    )
    updated_at: str | None = Field(
        default=None, description="When this record was last updated."
    )
