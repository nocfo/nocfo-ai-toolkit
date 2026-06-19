"""Schemas for draft bookkeeping suggestion inspection."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    AgentModel,
    BusinessContextInput,
    tool_handle,
)


class DocumentActiveSuggestionRetrieveInput(BusinessContextInput):
    tool_handle: str = Field(
        description=(
            "Value copied from bookkeeping_documents_list.items[].tool_handle or "
            "bookkeeping_document_retrieve.tool_handle for the draft document. "
            "Pass it unchanged to bookkeeping_document_active_suggestion_retrieve."
        )
    )


class DocumentSuggestionWarning(AgentModel):
    status: str | None = Field(
        default=None,
        description="Stable machine-readable status for the suggestion warning.",
    )
    is_final: bool | None = Field(
        default=None,
        description="Always false because this suggestion is not final accounting.",
    )
    is_posted: bool | None = Field(
        default=None,
        description="Always false because this suggestion is not posted to accounting.",
    )
    should_affect_reporting: bool | None = Field(
        default=None,
        description="Always false until the draft suggestion is explicitly finalized.",
    )
    message: str | None = Field(
        default=None,
        description="Plain-language warning that this is only a non-final suggestion.",
    )
    usage_guidance: str | None = Field(
        default=None,
        description="How the AI should use this suggestion without confusing it with posted bookkeeping.",
    )


class DocumentSuggestionAction(AgentModel):
    id: str | None = Field(default=None, description="Stable action identifier.")
    tool_name: str | None = Field(
        default=None,
        description="Recommended MCP mutation tool for this suggestion.",
    )
    description: str | None = Field(
        default=None,
        description="What the suggested next action does.",
    )
    recommended: bool | None = Field(
        default=None,
        description="Whether this is the preferred next step.",
    )
    tool_handle: str | None = Field(
        default=None,
        description="Pass this unchanged to the recommended bookkeeping mutation tool when it targets the source document.",
    )
    document_number: str | int | None = Field(
        default=None,
        description="Owning document number for human reference.",
    )


class DraftSuggestionSourceDocument(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Pass this unchanged to bookkeeping_document_retrieve for the owning draft document.",
    )
    id: int | None = Field(default=None, description="Internal draft document ID.")
    number: str | int | None = Field(
        default=None,
        description="Draft bookkeeping document number visible to the user.",
    )
    is_draft: bool | None = Field(
        default=None,
        description="Should be true because active suggestions only exist for drafts.",
    )
    description: str | None = Field(
        default=None,
        description="Current draft document description.",
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


class DraftSuggestionPayload(AgentModel):
    suggestion_handle: str | None = Field(
        default=None,
        description="Stable handle for this active suggestion payload.",
    )
    id: int | None = Field(default=None, description="Internal suggestion ID.")
    key: str | None = Field(
        default=None,
        description="Backend suggestion key when available.",
    )
    state: str | None = Field(
        default=None,
        description="Suggestion lifecycle state, expected to be active.",
    )
    is_final: bool | None = Field(
        default=None,
        description="Always false because the suggestion is not final accounting.",
    )
    is_posted: bool | None = Field(
        default=None,
        description="Always false because the suggestion is not posted bookkeeping.",
    )
    detail_tool_name: str | None = Field(
        default=None,
        description="Current MCP tool name for retrieving this suggestion detail payload.",
    )
    date: str | None = Field(
        default=None, description="Suggestion date. Format: YYYY-MM-DD."
    )
    description: str | None = Field(
        default=None,
        description="Human-readable suggestion description.",
    )
    amount: Any | None = Field(
        default=None,
        description="Suggested amount inferred from transaction, receipt, or import evidence.",
    )
    blueprint: dict[str, Any] | None = Field(
        default=None,
        description="Suggested bookkeeping blueprint. This is informational until finalized.",
    )
    blueprint_type: str | None = Field(
        default=None,
        description="Resolved blueprint type for the suggested posting plan.",
    )
    contact_id: int | None = Field(
        default=None,
        description="Suggested contact ID when available.",
    )
    contact_name: str | None = Field(
        default=None,
        description="Suggested contact display name when available.",
    )
    attachment_ids: list[int] | None = Field(
        default=None,
        description="Attachments related to the suggestion evidence when available.",
    )
    tag_ids: list[int] | None = Field(
        default=None,
        description="Related tag IDs when available.",
    )
    ui_rows: list[dict[str, Any]] | None = Field(
        default=None,
        description="Entry preview rows derived from existing backend suggestion logic.",
    )
    source_account: dict[str, Any] | None = Field(
        default=None,
        description="Source payment account detected from the evidence when available.",
    )
    import_data: dict[str, Any] | None = Field(
        default=None,
        description="Supporting import/receipt/transaction evidence used to generate the suggestion.",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_suggestion_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "suggestion_handle" not in data and isinstance(raw_id, int):
            data["suggestion_handle"] = tool_handle(
                "bookkeeping_document_active_suggestion", raw_id
            )
        return data


class DocumentActiveSuggestionDetail(AgentModel):
    suggestion: DraftSuggestionPayload | None = Field(
        default=None,
        description="Full active suggestion details for the selected draft document.",
    )
    source_document: DraftSuggestionSourceDocument | None = Field(
        default=None,
        description="Draft bookkeeping document that owns this active suggestion.",
    )
    warning: DocumentSuggestionWarning | None = Field(
        default=None,
        description="Explicit warning that this suggestion is informational only and not posted.",
    )
    available_actions: list[DocumentSuggestionAction] | None = Field(
        default=None,
        description="Recommended next actions, usually including finalize of the active suggestion.",
    )

    @model_validator(mode="before")
    @classmethod
    def attach_document_number_to_actions(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        source_document = data.get("source_document")
        document_number = None
        document_handle = None
        if isinstance(source_document, dict):
            document_number = source_document.get("number")
            document_handle = source_document.get("tool_handle")
        actions = data.get("available_actions")
        if isinstance(actions, list):
            data["available_actions"] = [
                {
                    **action,
                    "document_number": action.get("document_number", document_number),
                    "tool_handle": action.get("tool_handle", document_handle),
                }
                if isinstance(action, dict)
                else action
                for action in actions
            ]
        return data
