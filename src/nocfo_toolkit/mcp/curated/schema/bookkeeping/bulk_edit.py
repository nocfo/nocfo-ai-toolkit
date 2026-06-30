"""Schemas for the general bulk document-edit MCP tool.

``bookkeeping_document_update`` applies one identical payload to every target, so it
cannot express changes that differ per document or are derived from each document's
own content — replace account X with Y wherever it appears, swap a VAT code, add or
remove a single tag, or give each document a *different* account/file.

``DocumentBulkEditInput`` supports two shapes, both resolved in one confirmed call:

* per-target mode (``documents``): a list of groups, each naming its own documents
  and the edits for them — so different documents can get different edits.
* uniform mode (``edits`` + a selector): the same edits applied to every document
  matched by tool_handles or filters.

New edit dimensions are added by introducing one more edit ``op``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BeforeValidator, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.batch import ToolHandleList, as_list
from nocfo_toolkit.mcp.curated.schema.common import BusinessContextInput, StrictModel


class ReplaceAccountEdit(StrictModel):
    op: Literal["replace_account"] = Field(
        description="Replace one bookkeeping account with another everywhere it appears in each document's blueprint (payment-account shortcuts and every entry row)."
    )
    from_account: int = Field(
        description="Existing user-facing account number to replace, e.g. 1910."
    )
    to_account: int = Field(
        description="New user-facing account number to use instead, e.g. 1031."
    )

    @model_validator(mode="after")
    def validate_accounts_differ(self) -> "ReplaceAccountEdit":
        if self.from_account == self.to_account:
            raise ValueError("from_account and to_account must differ.")
        return self


class ReplaceVatCodeEdit(StrictModel):
    op: Literal["replace_vat_code"] = Field(
        description="Replace a VAT code on every matching blueprint entry row. VAT code and rate are coupled; pass to_vat_rate when the new code implies a different rate. For valid values call constants_retrieve with kind=vat_codes and kind=vat_rates."
    )
    from_vat_code: int = Field(description="Existing VAT code to replace.")
    to_vat_code: int = Field(description="New VAT code to use instead.")
    to_vat_rate: float | int | None = Field(
        default=None,
        description="Optional VAT rate to set alongside the new code (e.g. 0, 10, 24, 25.5).",
    )

    @model_validator(mode="after")
    def validate_codes_differ(self) -> "ReplaceVatCodeEdit":
        if self.from_vat_code == self.to_vat_code and self.to_vat_rate is None:
            raise ValueError("from_vat_code and to_vat_code must differ.")
        return self


class ReplaceVatRateEdit(StrictModel):
    op: Literal["replace_vat_rate"] = Field(
        description="Replace a VAT rate on every matching blueprint entry row. For valid/effective rates call constants_retrieve with kind=vat_rates."
    )
    from_vat_rate: float | int = Field(description="Existing VAT rate to replace.")
    to_vat_rate: float | int = Field(description="New VAT rate to use instead.")

    @model_validator(mode="after")
    def validate_rates_differ(self) -> "ReplaceVatRateEdit":
        if float(self.from_vat_rate) == float(self.to_vat_rate):
            raise ValueError("from_vat_rate and to_vat_rate must differ.")
        return self


class SetContactEdit(StrictModel):
    op: Literal["set_contact"] = Field(
        description="Set the linked contact on the target document(s). Provide exactly one of contact (exact name) or contact_id."
    )
    contact: str | None = Field(default=None, description="Exact contact name to link.")
    contact_id: int | None = Field(
        default=None, description="Numeric contact ID to link."
    )

    @model_validator(mode="after")
    def validate_contact_reference(self) -> "SetContactEdit":
        if (self.contact is None) == (self.contact_id is None):
            raise ValueError("Provide exactly one of contact or contact_id.")
        return self


class AddTagsEdit(StrictModel):
    op: Literal["add_tags"] = Field(
        description="Add these tags to the target document(s) while keeping existing tags. Tags must already exist; create missing ones first with bookkeeping_tag_create."
    )
    tag_names: list[str] = Field(description="Existing business tag names to add.")


class RemoveTagsEdit(StrictModel):
    op: Literal["remove_tags"] = Field(
        description="Remove these tags from the target document(s) while keeping other tags."
    )
    tag_names: list[str] = Field(description="Business tag names to remove if present.")


class SetTagsEdit(StrictModel):
    op: Literal["set_tags"] = Field(
        description="Replace the full tag set of the target document(s) with exactly these tags."
    )
    tag_names: list[str] = Field(
        description="Business tag names to set as the new full set."
    )


class AddAttachmentsEdit(StrictModel):
    op: Literal["add_attachments"] = Field(
        description="Attach these uploaded files to the target document(s) while keeping existing attachments. Files usually belong to one specific document, so prefer per-target mode (a separate group per document). Review a file with bookkeeping_file_retrieve before attaching."
    )
    file_ids: list[int] = Field(
        description="File ids to attach (from bookkeeping_file_upload or bookkeeping_files_list)."
    )


class RemoveAttachmentsEdit(StrictModel):
    op: Literal["remove_attachments"] = Field(
        description="Detach these files from the target document(s) while keeping other attachments."
    )
    file_ids: list[int] = Field(description="File ids to detach if present.")


class SetAttachmentsEdit(StrictModel):
    op: Literal["set_attachments"] = Field(
        description="Replace the full attachment set of the target document(s) with exactly these files."
    )
    file_ids: list[int] = Field(
        description="File ids to set as the new full attachment list."
    )


class SetDescriptionEdit(StrictModel):
    op: Literal["set_description"] = Field(
        description="Set the document-level description to a fixed value on the target document(s)."
    )
    description: str = Field(description="New document description.")


class ReplaceDescriptionEdit(StrictModel):
    op: Literal["replace_description"] = Field(
        description="Find-and-replace within the document-level description text of the target document(s) (documents whose description does not contain find are left unchanged)."
    )
    find: str = Field(description="Substring to find in the current description.")
    replace: str = Field(description="Replacement substring.")


class SetDateEdit(StrictModel):
    op: Literal["set_date"] = Field(
        description="Set the document date on the target document(s). Format: YYYY-MM-DD."
    )
    date: str = Field(description="New document date. Format: YYYY-MM-DD.")


DocumentEdit = Annotated[
    Union[
        ReplaceAccountEdit,
        ReplaceVatCodeEdit,
        ReplaceVatRateEdit,
        SetContactEdit,
        AddTagsEdit,
        RemoveTagsEdit,
        SetTagsEdit,
        AddAttachmentsEdit,
        RemoveAttachmentsEdit,
        SetAttachmentsEdit,
        SetDescriptionEdit,
        ReplaceDescriptionEdit,
        SetDateEdit,
    ],
    Field(discriminator="op"),
]


class DocumentEditGroup(StrictModel):
    tool_handles: ToolHandleList = Field(
        description="One or more document tool_handles that THIS group's edits apply to (from bookkeeping_documents_list or bookkeeping_document_retrieve)."
    )
    edits: Annotated[list[DocumentEdit], BeforeValidator(as_list)] = Field(
        description="Edits to apply to this group's documents, each computed from each document's current content.",
        min_length=1,
    )


class DocumentBulkEditInput(BusinessContextInput):
    """Apply per-target or uniform document edits, all in one confirmed call."""

    documents: list[DocumentEditGroup] | None = Field(
        default=None,
        description="Per-target edits: a list of groups, each naming its own documents and the edits for them. Use this when DIFFERENT documents need DIFFERENT changes (e.g. document A's account to 1090, documents B-D's account to 1091, attach file 7 to document A) — all applied in one confirmation. For the SAME change across a set, use uniform mode (edits + a selector) instead.",
    )
    edits: Annotated[list[DocumentEdit] | None, BeforeValidator(as_list)] = Field(
        default=None,
        description="Uniform mode: one or more edits applied identically to every document matched by the selector below. For different edits per document, use `documents` instead.",
    )
    tool_handles: Annotated[list[str] | None, BeforeValidator(as_list)] = Field(
        default=None,
        description="Uniform mode selector: explicit document tool_handles to edit (a lone handle is also accepted). Omit to select by the filters below.",
    )
    document_number: str | None = Field(
        default=None, description="Bookkeeping document number visible to the user."
    )
    date_from: str | None = Field(
        default=None,
        description="Start date for a date range, inclusive. Format: YYYY-MM-DD.",
    )
    date_to: str | None = Field(
        default=None,
        description="End date for a date range, inclusive. Format: YYYY-MM-DD.",
    )
    contact_id: int | None = Field(
        default=None, description="Filter documents by linked contact ID."
    )
    account_number: int | None = Field(
        default=None,
        description="Select documents that use this account number, e.g. 1910. Omit when a replace_account edit already names the account to change.",
    )
    vat_code: int | None = Field(
        default=None, description="Select documents whose entries use this VAT code."
    )
    vat_rate: float | int | None = Field(
        default=None, description="Select documents whose entries use this VAT rate."
    )
    is_draft: bool | None = Field(
        default=None, description="Whether the document is still a draft."
    )
    is_locked: bool | None = Field(
        default=None,
        description="True selects locked documents (which cannot be edited until unlocked).",
    )
    is_flagged: bool | None = Field(
        default=None, description="Whether the document is flagged for attention."
    )
    query: str | None = Field(
        default=None, description="Free-text search to narrow the selected documents."
    )

    @model_validator(mode="after")
    def validate_mode(self) -> "DocumentBulkEditInput":
        per_target = self.documents is not None
        uniform = self.edits is not None
        if per_target == uniform:
            raise ValueError(
                "Provide either `documents` (different edits per document) or `edits` "
                "(the same edits across a selection), but not both."
            )
        if per_target and not self.documents:
            raise ValueError("`documents` must contain at least one group.")
        if per_target and (self.tool_handles or self.has_filters()):
            raise ValueError(
                "When using `documents`, put each group's targets inside the group; "
                "do not also set tool_handles or filters."
            )
        if uniform and not self.edits:
            raise ValueError("`edits` must contain at least one edit.")
        return self

    def has_filters(self) -> bool:
        return any(
            value is not None
            for value in (
                self.document_number,
                self.date_from,
                self.date_to,
                self.contact_id,
                self.account_number,
                self.vat_code,
                self.vat_rate,
                self.is_draft,
                self.is_locked,
                self.is_flagged,
                self.query,
            )
        )

    def filter_params(self) -> dict[str, Any]:
        """Backend list query params (account_number is resolved to an id by the tool)."""
        params = {
            "number": self.document_number,
            "search": self.query,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "contact": self.contact_id,
            "account_number": self.account_number,
            "vat_code": self.vat_code,
            "vat_rate": self.vat_rate,
            "is_draft": self.is_draft,
            "is_locked": self.is_locked,
            "is_flagged": self.is_flagged,
        }
        return {key: value for key, value in params.items() if value is not None}
