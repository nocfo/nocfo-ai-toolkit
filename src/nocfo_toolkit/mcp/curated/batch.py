"""Sequential, best-effort batch runner for mutating curated MCP tools.

One tool call targets many resources, so one confirmation covers the whole batch.
Each target runs the tool's existing single-target logic; a failing target is
captured as a failed result instead of aborting the batch.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastmcp.exceptions import ToolError

from nocfo_toolkit.mcp.curated.errors import raise_tool_error
from nocfo_toolkit.mcp.curated.schemas import (
    BatchItemResult,
    BatchResponse,
    ToolErrorPayload,
    dump_model,
)


def _error_payload(exc: ToolError) -> ToolErrorPayload:
    raw = exc.args[0] if exc.args else str(exc)
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict):
        try:
            return ToolErrorPayload.model_validate(data)
        except Exception:  # noqa: BLE001 - fall back to a plain message payload
            pass
    return ToolErrorPayload(error_type="tool_error", message=str(raw))


async def run_batch(
    targets: Sequence[Any],
    handler: Callable[[Any], Awaitable[dict[str, Any]]],
    *,
    label: Callable[[Any], Any] = lambda target: target,
) -> dict[str, Any]:
    """Run ``handler`` for each target, aggregating per-target results.

    ``handler`` returns the same dict a single-target tool would return.
    ``label`` maps a target to the value echoed back in ``results[].target``.
    """
    if not targets:
        raise_tool_error(
            "invalid_request",
            "No targets provided for this batch operation.",
            "Provide at least one target (id, number, tool_handle, or payload).",
            status_code=400,
        )
    results: list[BatchItemResult] = []
    for target in targets:
        # Resolve the echo key once, fault-isolated, so a misbehaving label callable
        # can never abort the batch or mislabel a target across branches.
        try:
            key = label(target)
        except Exception:  # noqa: BLE001 - labelling must never abort the batch
            key = None
        try:
            payload = await handler(target)
            results.append(BatchItemResult(ok=True, target=key, result=payload))
        except ToolError as exc:
            results.append(
                BatchItemResult(ok=False, target=key, error=_error_payload(exc))
            )
        except Exception as exc:  # noqa: BLE001 - isolate unexpected per-target failures
            # Keep the batch best-effort: a non-ToolError (e.g. response validation
            # or transport error) on one target must not discard the results of the
            # targets already processed. CancelledError/KeyboardInterrupt are
            # BaseException and intentionally still propagate.
            results.append(
                BatchItemResult(
                    ok=False,
                    target=key,
                    error=ToolErrorPayload(
                        error_type="internal_error",
                        message=str(exc) or exc.__class__.__name__,
                    ),
                )
            )
    succeeded = sum(1 for item in results if item.ok)
    return dump_model(
        BatchResponse(
            total=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
        )
    )
