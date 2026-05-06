"""Bookkeeping document, entry, and relation schemas."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    AgentModel,
    BusinessContextInput,
    BusinessPaginationInput,
    DocumentAction,
    DocumentSide,
    RelationRole,
    StrictModel,
    RelationType,
    enum_or_str,
    tool_handle,
)


class DocumentNumberInput(BusinessContextInput):
    document_number: str = Field(
        description="Bookkeeping document number visible to the user."
    )


class DocumentNumberPayloadInput(DocumentNumberInput):
    payload: dict[str, Any] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class AgentBlueprintEntryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    account_id: int | str | None = Field(default=None)
    account_number: int | str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_account_reference(self) -> "AgentBlueprintEntryPayload":
        if self.account_id is not None and self.account_number is not None:
            raise ValueError("Provide only one of account_id or account_number.")
        return self


class AgentDocumentBlueprintPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    debet_account_id: int | str | None = Field(default=None)
    debet_account_number: int | str | None = Field(default=None)
    credit_account_id: int | str | None = Field(default=None)
    credit_account_number: int | str | None = Field(default=None)
    debet_entries: list[Any] | None = Field(default=None)
    credit_entries: list[Any] | None = Field(default=None)
    expense_entries: list[Any] | None = Field(default=None)

    @model_validator(mode="after")
    def validate_top_level_account_references(self) -> "AgentDocumentBlueprintPayload":
        if self.debet_account_id is not None and self.debet_account_number is not None:
            raise ValueError(
                "Provide only one of debet_account_id or debet_account_number."
            )
        if (
            self.credit_account_id is not None
            and self.credit_account_number is not None
        ):
            raise ValueError(
                "Provide only one of credit_account_id or credit_account_number."
            )
        return self


class DocumentMutationPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    contact_id: Any | None = Field(default=None)
    contact: str | None = Field(default=None)
    tag_names: list[str] | None = Field(default=None)
    tag_ids: list[int] | None = Field(default=None)
    blueprint: dict[str, Any] | None = Field(
        default=None,
        description="Editable posting plan. Required for bookkeeping document writes. For blueprint structure and required fields, call docs_retrieve with kind=blueprint. For valid VAT code/rate values used in blueprint rows, call constants_retrieve with kind=vat_codes and kind=vat_rates.",
    )

    @model_validator(mode="after")
    def validate_contact_reference(self) -> "DocumentMutationPayload":
        if self.contact is not None and self.contact_id is not None:
            raise ValueError("Provide only one of contact or contact_id.")
        return self


class DocumentCreatePayload(DocumentMutationPayload):
    blueprint: dict[str, Any] = Field(
        description="Editable posting plan required for bookkeeping document creation. For blueprint structure, call docs_retrieve with kind=blueprint. For VAT code/rate options used in blueprint rows, call constants_retrieve with kind=vat_codes and kind=vat_rates."
    )


class DocumentMutationInput(BusinessContextInput):
    payload: DocumentCreatePayload = Field(
        description="Bookkeeping document write payload. blueprint is required."
    )


class DocumentNumberMutationInput(DocumentNumberInput):
    payload: DocumentMutationPayload = Field(
        description="Bookkeeping document write payload. blueprint is required."
    )


class TagNamesInput(DocumentNumberInput):
    tag_names: list[str] = Field(
        description="Tag names to filter by or apply to the document."
    )


class DocumentListInput(BusinessPaginationInput):
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
        default=None,
        description="Contact ID filter. Use invoicing_contact_retrieve to expand this ID to contact details.",
    )
    account_number: int | None = Field(
        default=None, description="User-facing bookkeeping account number, e.g. 1910."
    )
    is_draft: bool | None = Field(
        default=None, description="Whether the bookkeeping document is still a draft."
    )
    is_locked: bool | None = Field(
        default=None,
        description="True when the record is locked and should not be changed before unlocking.",
    )
    is_flagged: bool | None = Field(
        default=None, description="Whether the document has been flagged for attention."
    )

    def query_params(self) -> dict[str, Any]:
        params = {
            "number": self.document_number,
            "search": self.query,
            "date_gte": self.date_from,
            "date_lte": self.date_to,
            "contact": self.contact_id,
            "account_number": self.account_number,
            "is_draft": self.is_draft,
            "is_locked": self.is_locked,
            "is_flagged": self.is_flagged,
        }
        return {key: value for key, value in params.items() if value is not None}


class DocumentRetrieveInput(BusinessContextInput):
    tool_handle: str = Field(
        description="Value copied from bookkeeping_documents_list.items[].tool_handle or related_document_handle/document_handle fields. Pass it unchanged to bookkeeping_document_retrieve; do not use document numbers or database IDs here."
    )


class DocumentActionInput(DocumentNumberInput):
    action: enum_or_str(DocumentAction) = Field(
        description="Action to run on the selected resource."
    )


class EntryListInput(DocumentNumberInput):
    limit: int = Field(
        default=50, description="Maximum number of records to return in this page."
    )
    cursor: str | None = Field(
        default=None,
        description="Cursor from the previous page_info.next_cursor for the same list tool.",
    )


class DocumentRelationCreateInput(DocumentNumberInput):
    related_document_number: str = Field(
        description="Document number of the other bookkeeping document in the relation."
    )
    role: enum_or_str(RelationRole) = Field(
        description="Whether the current document is the accrual or settlement side of the relation."
    )
    type: enum_or_str(RelationType) = Field(
        default=RelationType.accrual_pair,
        description="Type/category shown for this record.",
    )


class DocumentRelationIdInput(DocumentNumberInput):
    relation_id: int = Field(
        description="Relation ID from bookkeeping_document_relations_list. Use bookkeeping_document_relation_update or bookkeeping_document_relation_delete for this ID."
    )


class DocumentRelationUpdatePayload(StrictModel):
    related_document_number: str | None = Field(
        default=None,
        description="Document number of the other bookkeeping document in the relation.",
    )
    role: enum_or_str(RelationRole) | None = Field(
        default=None,
        description="Whether the current document is the accrual or settlement side of the relation.",
    )
    type: enum_or_str(RelationType) | None = Field(
        default=None,
        description="Type/category shown for this record.",
    )


class DocumentRelationUpdateInput(DocumentRelationIdInput):
    payload: DocumentRelationUpdatePayload = Field(
        description="Relation update payload. Supported fields: related_document_number, role, and type."
    )


class DocumentSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from bookkeeping_documents_list.items[].tool_handle and pass it unchanged to bookkeeping_document_retrieve.",
    )
    number: str | int | None = Field(
        default=None, description="Bookkeeping document number visible to the user."
    )
    date: str | None = Field(
        default=None, description="Bookkeeping document date. Format: YYYY-MM-DD."
    )
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    contact_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("contact_id", "contact"),
        description="Linked contact ID. Use invoicing_contact_retrieve to expand this ID to contact details.",
    )
    contact_name: str | None = Field(
        default=None, description="Display name of the linked contact."
    )
    is_draft: bool | None = Field(
        default=None, description="Whether the bookkeeping document is still a draft."
    )
    is_locked: bool | None = Field(
        default=None,
        description="True when the record is locked and should not be changed before unlocking.",
    )
    is_flagged: bool | None = Field(
        default=None, description="Whether the document has been flagged for attention."
    )
    balance: Any | None = Field(
        default=None, description="Current balance shown for this record."
    )
    workflow: Any | None = Field(
        default=None,
        description="Current document workflow state and next-action metadata.",
    )
    suggestion_info: Any | None = Field(
        default=None,
        description="Compact information about the active accounting suggestion.",
    )
    available_actions: Any | None = Field(
        default=None, description="Actions currently available for the document."
    )
    blueprint_type: str | None = Field(
        default=None,
        description="Type of editable bookkeeping blueprint for the document.",
    )
    attachment_count: int | None = Field(
        default=None, description="Number of files attached to the document."
    )
    tag_count: int | None = Field(
        default=None, description="Number of tags attached to the document."
    )
    relation_count: int | None = Field(
        default=None, description="Number of document relations."
    )

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("bookkeeping_document", raw_id)
        return data

    @model_validator(mode="before")
    @classmethod
    def derive_counts(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for name in ("attachments", "attachment_ids"):
            if isinstance(data.get(name), list):
                data.setdefault("attachment_count", len(data[name]))
        if isinstance(data.get("tag_ids"), list):
            data.setdefault("tag_count", len(data["tag_ids"]))
        if isinstance(data.get("relations"), list):
            data.setdefault("relation_count", len(data["relations"]))
        return data


class DocumentListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to bookkeeping_document_retrieve. Do not edit or derive it from document numbers.",
    )
    number: str | int | None = Field(
        default=None, description="Bookkeeping document number visible to the user."
    )
    date: str | None = Field(
        default=None, description="Bookkeeping document date. Format: YYYY-MM-DD."
    )
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    contact_name: str | None = Field(
        default=None, description="Display name of the linked contact."
    )
    is_draft: bool | None = Field(
        default=None, description="Whether the document is still a draft."
    )
    is_locked: bool | None = Field(
        default=None, description="Whether the document is locked."
    )
    is_flagged: bool | None = Field(
        default=None, description="Whether the document is flagged."
    )
    attachment_count: int | None = Field(
        default=None, description="Number of linked files."
    )
    tag_count: int | None = Field(default=None, description="Number of linked tags.")
    relation_count: int | None = Field(
        default=None, description="Number of linked relations."
    )

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("bookkeeping_document", raw_id)
        return data

    @model_validator(mode="before")
    @classmethod
    def derive_counts(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for name in ("attachments", "attachment_ids"):
            if isinstance(data.get(name), list):
                data.setdefault("attachment_count", len(data[name]))
        if isinstance(data.get("tag_ids"), list):
            data.setdefault("tag_count", len(data["tag_ids"]))
        if isinstance(data.get("relations"), list):
            data.setdefault("relation_count", len(data["relations"]))
        return data


class DocumentDetail(DocumentSummary):
    blueprint: Any | None = Field(
        default=None,
        description="Editable posting plan. Change blueprint fields to change generated entries. For detailed blueprint guidance, use docs_retrieve with kind=blueprint. For VAT code/rate values shown in blueprint/entries, use constants_retrieve with kind=vat_codes and kind=vat_rates.",
    )
    entry_summary: list[dict[str, Any]] | None = Field(
        default=None,
        description="Generated journal entries to verify after creating or updating the blueprint.",
    )
    tag_ids: list[int] | None = Field(
        default=None, description="Tag IDs currently attached to the document."
    )
    relations: Any | None = Field(
        default=None, description="Relations linking this document to other documents."
    )


class EntrySummary(AgentModel):
    entry_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("entry_id", "id"),
        description="Entry ID for this generated journal entry.",
    )
    account_number: int | None = Field(
        default=None, description="User-facing bookkeeping account number, e.g. 1910."
    )
    account_name: str | None = Field(
        default=None, description="Display name of the bookkeeping account."
    )
    side: enum_or_str(DocumentSide) | None = Field(
        default=None, description="Debit or credit side of the journal entry."
    )
    amount: Any | None = Field(
        default=None, description="Monetary amount for this entry."
    )
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    vat_code: Any | None = Field(
        default=None,
        description="VAT code associated with this row or entry. To see valid VAT codes, call constants_retrieve with kind=vat_codes.",
    )
    vat_rate: Any | None = Field(
        default=None,
        description="VAT rate associated with this row or entry. To see valid/effective VAT rates, call constants_retrieve with kind=vat_rates (date_at required).",
    )

    @model_validator(mode="before")
    @classmethod
    def derive_side(cls, value: Any) -> Any:
        if isinstance(value, dict) and "side" not in value and "is_debet" in value:
            data = dict(value)
            data["side"] = (
                DocumentSide.debit.value
                if data.get("is_debet")
                else DocumentSide.credit.value
            )
            return data
        return value


class RelationSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from bookkeeping_document_relations_list.items[].tool_handle and pass it unchanged to bookkeeping_document_relation_update or bookkeeping_document_relation_delete.",
    )
    relation_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("relation_id", "id"),
        description="Relation ID. Use bookkeeping_document_relation_update or bookkeeping_document_relation_delete for this ID.",
    )
    related_document_handle: str | None = Field(
        default=None,
        description="Value copied from the relation payload for the linked document. Pass it unchanged to bookkeeping_document_retrieve.",
    )
    document_number: str | int | None = Field(
        default=None, description="Bookkeeping document number visible to the user."
    )
    related_document_number: str | int | None = Field(
        default=None,
        description="Document number of the other bookkeeping document in the relation.",
    )
    direction: str | None = Field(
        default=None,
        description="Direction of the relation relative to the current document.",
    )
    type: enum_or_str(RelationType) | None = Field(
        default=None,
        description="Type/category shown for this record.",
    )
    current_document_role: enum_or_str(RelationRole) | None = Field(
        default=None,
        validation_alias=AliasChoices("current_document_role", "role"),
        description="Role of the current document in a relation.",
    )
    related_document_role: enum_or_str(RelationRole) | None = Field(
        default=None, description="Role of the related document in a relation."
    )
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    reason: str | None = Field(
        default=None, description="Reason this relation was suggested or created."
    )
    score: float | None = Field(
        default=None, description="Confidence score for this suggested relation."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_relation_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "relation_id" not in data and isinstance(data.get("id"), int):
            data["relation_id"] = data["id"]
        related = data.get("related_document")
        if isinstance(related, dict):
            if (
                "related_document_number" not in data
                and related.get("number") is not None
            ):
                data["related_document_number"] = related.get("number")
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handles(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        relation_id = data.get("relation_id")
        if "tool_handle" not in data and isinstance(relation_id, int):
            data["tool_handle"] = tool_handle("bookkeeping_relation", relation_id)
        related = data.get("related_document")
        related_id: int | None = None
        if isinstance(related, dict) and isinstance(related.get("id"), int):
            related_id = related["id"]
        elif isinstance(related, int):
            related_id = related
        if "related_document_handle" not in data and isinstance(related_id, int):
            data["related_document_handle"] = tool_handle(
                "bookkeeping_document", related_id
            )
        return data
