from __future__ import annotations

import pytest

from nocfo_toolkit.mcp import (
    assert_openapi_mcp_contract_valid,
    validate_openapi_mcp_contract,
)


def test_validate_openapi_mcp_contract_success() -> None:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "NoCFO", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/v1/list/": {
                "get": {
                    "operationId": "bookkeeping.items.list",
                    "tags": ["MCP"],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/v1/item/{id}/": {
                "get": {
                    "operationId": "bookkeeping.item.retrieve",
                    "tags": ["MCP"],
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/v1/item/": {
                "post": {
                    "operationId": "bookkeeping.item.create",
                    "tags": ["MCP"],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }

    result = validate_openapi_mcp_contract(spec, validate_output=False)

    assert result.is_valid is True
    assert result.mcp_operation_count == 3
    assert result.tool_count == 3
    assert result.resource_count == 0
    assert result.resource_template_count == 0
    assert result.issues == ()


def test_validate_openapi_mcp_contract_flags_missing_operation_id() -> None:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "NoCFO", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/v1/item/": {
                "post": {
                    "tags": ["MCP"],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    result = validate_openapi_mcp_contract(spec)

    assert result.is_valid is False
    assert result.missing_operation_ids_in_schema == ("POST /v1/item/",)
    assert any("missing operationId" in issue for issue in result.issues)


def test_assert_openapi_mcp_contract_valid_raises_for_invalid_contract() -> None:
    invalid_spec = {
        "openapi": "3.0.0",
        "info": {"title": "NoCFO", "version": "1.0.0"},
        "paths": {
            "/v1/item/": {
                "post": {
                    "tags": ["MCP"],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    with pytest.raises(AssertionError, match="missing operationId"):
        assert_openapi_mcp_contract_valid(invalid_spec)
