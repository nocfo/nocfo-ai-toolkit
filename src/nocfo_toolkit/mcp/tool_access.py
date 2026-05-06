"""Tool access profile helpers for split MCP HTTP endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from typing import Generator, Iterable


class ToolAccessProfile(StrEnum):
    """Endpoint-specific tool visibility/call policy."""

    ALL = "all"
    READ = "read"
    WRITE = "write"


class ToolTag(StrEnum):
    """Canonical tool tags used by NoCFO MCP routing."""

    READ_ONLY = "read_only"


_CURRENT_TOOL_ACCESS_PROFILE: ContextVar[ToolAccessProfile] = ContextVar(
    "nocfo_mcp_tool_access_profile",
    default=ToolAccessProfile.ALL,
)


@contextmanager
def request_tool_access_profile(
    profile: ToolAccessProfile,
) -> Generator[None, None, None]:
    """Scope current request profile for filtering and call authorization."""
    token = _CURRENT_TOOL_ACCESS_PROFILE.set(profile)
    try:
        yield
    finally:
        _CURRENT_TOOL_ACCESS_PROFILE.reset(token)


def current_request_tool_access_profile() -> ToolAccessProfile:
    """Read current request profile."""
    return _CURRENT_TOOL_ACCESS_PROFILE.get()


def is_read_only_tool(tags: Iterable[str] | None) -> bool:
    """Return True when tool tags include read-only marker."""
    if not tags:
        return False
    normalized = {str(tag).strip().lower() for tag in tags}
    return ToolTag.READ_ONLY.value in normalized


def is_tool_allowed_for_request_profile(
    *,
    tags: Iterable[str] | None,
    profile: ToolAccessProfile,
) -> bool:
    """Check whether a tool is callable under the requested profile."""
    if profile is ToolAccessProfile.ALL:
        return True
    is_read_only = is_read_only_tool(tags)
    if profile is ToolAccessProfile.READ:
        return is_read_only
    return not is_read_only
