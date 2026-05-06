"""Interactive confirmation helpers for mutating curated tools."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastmcp.server.dependencies import get_context
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from pydantic import BaseModel

from nocfo_toolkit.mcp.curated.errors import raise_tool_error

_APPROVE_CHOICES = {
    "approve",
    "yes",
    "y",
    "kylla",
    "kyllä",
}


class MutationConfirmationChoice(BaseModel):
    id: Literal["approve", "cancel"]
    title: str


class MutationConfirmationTargetResource(BaseModel):
    type: str
    id: str | int


class MutationConfirmationEnvelope(BaseModel):
    kind: Literal["mutation_confirmation"] = "mutation_confirmation"
    version: int = 1
    business: str
    tool: str
    target_resource: MutationConfirmationTargetResource | None = None
    choices: list[MutationConfirmationChoice]
    parameters: dict[str, Any] | None = None


async def confirm_mutation(
    *,
    business: str,
    tool_name: str,
    target_resource: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
) -> None:
    """Request user approval for mutating operations when elicitation is available."""
    resolved_business = business.strip()
    if not resolved_business:
        raise_tool_error(
            "invalid_request",
            "Mutation confirmation requires business scope.",
            "Pass a non-empty business slug.",
        )
    resolved_tool_name = tool_name.strip()
    if not resolved_tool_name:
        raise_tool_error(
            "invalid_request",
            "Mutation confirmation requires tool name.",
            "Pass the current MCP tool name.",
        )
    fastmcp_context = get_context()

    envelope = MutationConfirmationEnvelope(
        tool=resolved_tool_name,
        business=resolved_business,
        target_resource=(
            MutationConfirmationTargetResource.model_validate(target_resource)
            if target_resource is not None
            else None
        ),
        choices=[
            MutationConfirmationChoice(id="approve", title="Approve"),
            MutationConfirmationChoice(id="cancel", title="Cancel"),
        ],
        parameters=parameters if parameters is not None else None,
    )
    elicit_message = (
        "[[NOCFO_ELICIT_V1]]\n"
        f"{json.dumps(envelope.model_dump(exclude_none=True), ensure_ascii=False)}\n"
        "[[/NOCFO_ELICIT_V1]]"
    )
    try:
        result = await fastmcp_context.elicit(
            message=elicit_message,
            response_type={
                "approve": {"title": "Approve"},
                "cancel": {"title": "Cancel"},
            },
        )
    except Exception:
        _raise_not_supported()

    match result:
        case AcceptedElicitation(data=data) if _is_approved_choice(data):
            return
        case AcceptedElicitation():
            _raise_cancelled()
        case DeclinedElicitation():
            _raise_cancelled()
        case CancelledElicitation():
            _raise_cancelled()
        case _:
            _raise_cancelled()


def _is_approved_choice(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _APPROVE_CHOICES


def _raise_not_supported() -> None:
    raise_tool_error(
        "mutation_not_supported",
        "Mutating action is not supported.",
        "Use an MCP client with elicitation support or disable approvals for this environment.",
    )


def _raise_cancelled() -> None:
    raise_tool_error(
        "mutation_cancelled",
        "Mutating action was cancelled by user.",
        "Retry and approve the action to continue.",
    )
