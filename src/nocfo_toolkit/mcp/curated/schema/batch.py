"""Shared schemas for batch (mass) mutating MCP tools.

Mutating curated tools accept one or more targets in a single call so that one
confirmation covers the whole batch. These reusable input models pluralise the
single-target selector, and the response models report a per-target outcome.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from nocfo_toolkit.mcp.curated.schema.common import (
    BusinessContextInput,
    StrictModel,
    ToolErrorPayload,
)


def as_list(value: Any) -> Any:
    """Coerce a lone scalar into a one-item list so single targets still work."""
    if value is None:
        return value
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


# Reusable plural-target field types (a lone scalar is coerced to a 1-item list).
ToolHandleList = Annotated[list[str], BeforeValidator(as_list)]
IntList = Annotated[list[int], BeforeValidator(as_list)]
StrList = Annotated[list[str], BeforeValidator(as_list)]
NumberList = Annotated[list[int | str], BeforeValidator(as_list)]
DictList = Annotated[list[dict[str, Any]], BeforeValidator(as_list)]

_TARGETS_HINT = (
    "Provide ALL targets here to act on them in a single confirmed call; "
    "a lone value is also accepted."
)
_SHARED_PAYLOAD_HINT = (
    "Fields to update, applied identically to every target in this call. "
    "Prefer user-facing values such as account_number, document_number, "
    "invoice_number, tag_names, or contact names when supported."
)
_PAYLOADS_HINT = (
    "List of create payloads; one entry per record to create in this call. "
    "Each entry is independent and uses the same fields as the single-create form."
)


class ToolHandlesInput(BusinessContextInput):
    tool_handles: ToolHandleList = Field(
        description=f"One or more tool_handle values from a list response. {_TARGETS_HINT}"
    )


class AccountNumbersInput(BusinessContextInput):
    account_numbers: IntList = Field(
        description=f"One or more user-facing bookkeeping account numbers, e.g. 1910. {_TARGETS_HINT}"
    )


class AccountNumbersPayloadInput(AccountNumbersInput):
    payload: dict[str, Any] = Field(description=_SHARED_PAYLOAD_HINT)


class IdentifiersInput(BusinessContextInput):
    identifiers: StrList = Field(
        description=f"One or more resource identifiers (ID or exact code/name). {_TARGETS_HINT}"
    )


class IdentifiersPayloadInput(IdentifiersInput):
    payload: dict[str, Any] = Field(description=_SHARED_PAYLOAD_HINT)


class IdsInput(BusinessContextInput):
    ids: IntList = Field(
        description=f"One or more resource IDs from the matching list tool. {_TARGETS_HINT}"
    )


class IdsPayloadInput(IdsInput):
    payload: dict[str, Any] = Field(description=_SHARED_PAYLOAD_HINT)


class InvoiceNumbersInput(BusinessContextInput):
    invoice_numbers: NumberList = Field(
        description=f"One or more invoice numbers visible to the user. {_TARGETS_HINT}"
    )


class InvoiceNumbersPayloadInput(InvoiceNumbersInput):
    payload: dict[str, Any] = Field(description=_SHARED_PAYLOAD_HINT)


class PayloadsInput(BusinessContextInput):
    payloads: DictList = Field(description=_PAYLOADS_HINT)


class BatchItemResult(StrictModel):
    ok: bool = Field(description="True when this target succeeded.")
    target: Any | None = Field(
        default=None,
        description="The target this result belongs to (tool_handle, number, id, or a "
        "natural key such as name/code for creates). Absent only for creates with no "
        "natural key; results are always returned in input order.",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Success payload for this target, same shape the single-target tool returns.",
    )
    error: ToolErrorPayload | None = Field(
        default=None,
        description="Error details when ok is false. Inspect error_type/message before retrying.",
    )


class BatchResponse(StrictModel):
    total: int = Field(description="Number of targets in this batch.")
    succeeded: int = Field(description="Number of targets that succeeded.")
    failed: int = Field(
        description="Number of targets that failed. Batches are applied per target and "
        "are NOT atomic: targets that already succeeded stay applied when others fail. "
        "When > 0, retry ONLY the failed target values in a new batched call — do not "
        "re-run the whole batch."
    )
    results: list[BatchItemResult] = Field(
        description="Per-target outcome, in the same order the targets were given."
    )
