"""Contract validation helpers for MCP OpenAPI compatibility."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from fastmcp.server.providers.openapi import OpenAPIProvider

from nocfo_toolkit.mcp.server import (
    MCP_OPENAPI_ROUTE_MAPS,
    apply_mcp_operation_metadata,
    apply_mcp_namespace_names,
    restore_openapi_output_schema,
)
from nocfo_toolkit.openapi import filter_mcp_spec


@dataclass(frozen=True)
class MCPContractValidationResult:
    """Result for validating OpenAPI-to-MCP component mapping."""

    is_valid: bool
    mcp_operation_count: int
    tool_count: int
    resource_count: int
    resource_template_count: int
    missing_in_provider: tuple[str, ...]
    unexpected_in_provider: tuple[str, ...]
    missing_operation_ids_in_schema: tuple[str, ...]
    issues: tuple[str, ...]


def _apply_component_mcp_metadata(route: Any, component: Any) -> None:
    apply_mcp_namespace_names(route, component)
    apply_mcp_operation_metadata(route, component)
    restore_openapi_output_schema(route, component)


def _get_base_url(openapi_spec: dict[str, Any]) -> str:
    servers = openapi_spec.get("servers")
    if isinstance(servers, list):
        for server in servers:
            if isinstance(server, dict) and isinstance(server.get("url"), str):
                return server["url"]
    return "https://api.example.com"


def _collect_operation_ids(
    filtered_spec: dict[str, Any],
) -> tuple[list[str], list[str]]:
    operation_ids: list[str] = []
    missing_operation_ids: list[str] = []

    for path, methods in filtered_spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(operation_id)
            else:
                missing_operation_ids.append(f"{str(method).upper()} {path}")

    return operation_ids, missing_operation_ids


def _collect_provider_operation_ids(provider: OpenAPIProvider) -> list[str]:
    def _components(attr: str) -> dict[str, Any]:
        for candidate in (attr.lstrip("_"), attr):
            value = getattr(provider, candidate, None)
            if isinstance(value, dict):
                return value
        return {}

    ids: list[str] = []
    for component in _components("_tools").values():
        route = getattr(component, "_route", None)
        operation_id = getattr(route, "operation_id", None)
        if operation_id:
            ids.append(operation_id)
    for component in _components("_resources").values():
        route = getattr(component, "_route", None)
        operation_id = getattr(route, "operation_id", None)
        if operation_id:
            ids.append(operation_id)
    for component in _components("_templates").values():
        route = getattr(component, "_route", None)
        operation_id = getattr(route, "operation_id", None)
        if operation_id:
            ids.append(operation_id)
    return ids


def _build_result(
    *,
    expected_operation_ids: list[str],
    provider_operation_ids: list[str],
    missing_operation_ids_in_schema: list[str],
    provider: OpenAPIProvider,
) -> MCPContractValidationResult:
    def _components_count(attr: str) -> int:
        for candidate in (attr.lstrip("_"), attr):
            value = getattr(provider, candidate, None)
            if isinstance(value, dict):
                return len(value)
        return 0

    expected_set = set(expected_operation_ids)
    provider_set = set(provider_operation_ids)

    missing_in_provider = tuple(sorted(expected_set - provider_set))
    unexpected_in_provider = tuple(sorted(provider_set - expected_set))

    issues: list[str] = []
    if missing_operation_ids_in_schema:
        issues.append(
            "Some MCP-tagged operations are missing operationId: "
            + ", ".join(missing_operation_ids_in_schema)
        )
    if missing_in_provider:
        issues.append(
            "OperationIds missing in OpenAPIProvider: " + ", ".join(missing_in_provider)
        )
    if unexpected_in_provider:
        issues.append(
            "Unexpected operationIds in OpenAPIProvider: "
            + ", ".join(unexpected_in_provider)
        )

    return MCPContractValidationResult(
        is_valid=not issues,
        mcp_operation_count=len(expected_operation_ids),
        tool_count=_components_count("_tools"),
        resource_count=_components_count("_resources"),
        resource_template_count=_components_count("_templates"),
        missing_in_provider=missing_in_provider,
        unexpected_in_provider=unexpected_in_provider,
        missing_operation_ids_in_schema=tuple(missing_operation_ids_in_schema),
        issues=tuple(issues),
    )


def validate_openapi_mcp_contract(
    openapi_spec: dict[str, Any],
    *,
    validate_output: bool = False,
) -> MCPContractValidationResult:
    """Validate that MCP-tagged operations map cleanly to FastMCP components.

    This function is designed to be imported from external repos (like backend tests)
    through the published ``nocfo-cli`` package.
    """
    filtered_spec = filter_mcp_spec(openapi_spec, mcp_tag="MCP")
    expected_operation_ids, missing_operation_ids_in_schema = _collect_operation_ids(
        filtered_spec
    )

    client = httpx.AsyncClient(base_url=_get_base_url(openapi_spec))
    try:
        provider = OpenAPIProvider(
            openapi_spec=filtered_spec,
            client=client,
            route_maps=MCP_OPENAPI_ROUTE_MAPS,
            mcp_component_fn=_apply_component_mcp_metadata,
            validate_output=validate_output,
        )
        provider_operation_ids = _collect_provider_operation_ids(provider)
    finally:
        try:
            asyncio.run(client.aclose())
        except RuntimeError:
            # If already running in event loop, closing can be skipped in this sync helper.
            pass

    return _build_result(
        expected_operation_ids=expected_operation_ids,
        provider_operation_ids=provider_operation_ids,
        missing_operation_ids_in_schema=missing_operation_ids_in_schema,
        provider=provider,
    )


def assert_openapi_mcp_contract_valid(
    openapi_spec: dict[str, Any],
    *,
    validate_output: bool = False,
) -> MCPContractValidationResult:
    """Assert MCP contract validity and return the validation result."""
    result = validate_openapi_mcp_contract(
        openapi_spec,
        validate_output=validate_output,
    )
    if not result.is_valid:
        raise AssertionError("\n".join(result.issues))
    return result
