from __future__ import annotations

import asyncio
import httpx
import pytest

from fastmcp.server.providers.openapi import OpenAPIProvider
from starlette.testclient import TestClient

from nocfo_toolkit.config import OutputFormat, TokenSource, ToolkitConfig
from nocfo_toolkit.mcp.server import (
    MCP_OPENAPI_ROUTE_MAPS,
    X_NOCFO_MCP_SERVER_INSTRUCTIONS,
    X_MCP_NAMESPACE,
    apply_mcp_operation_metadata,
    apply_mcp_namespace_names,
    build_mcp_component_name,
    create_server,
    MCPServerOptions,
)
from nocfo_toolkit.mcp.invoice_app import (
    _build_form_defaults,
    _build_invoice_payload,
    _build_non_ui_form_payload,
    _build_prefab_form,
    _parse_tool_error,
)
from nocfo_toolkit.openapi import X_MCP_COMPONENT_TYPE, filter_mcp_spec


def test_filter_mcp_spec_keeps_only_mcp_tagged_operations() -> None:
    spec = {
        "paths": {
            "/v1/a/": {
                "get": {"tags": ["MCP"]},
                "post": {"tags": ["Internal"]},
            },
            "/v1/b/": {
                "get": {"tags": ["Public"]},
            },
        }
    }

    filtered = filter_mcp_spec(spec)

    assert "/v1/a/" in filtered["paths"]
    assert "get" in filtered["paths"]["/v1/a/"]
    assert "post" not in filtered["paths"]["/v1/a/"]
    assert "/v1/b/" not in filtered["paths"]


def test_create_server_requires_token() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
    )

    with pytest.raises(RuntimeError, match="Missing authentication token"):
        create_server(config)


def test_create_server_accepts_jwt_without_pat(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        lambda *, base_url: {
            "openapi": "3.0.0",
            "info": {"title": "NoCFO", "version": "1.0.0"},
            "servers": [{"url": base_url}],
            "paths": {
                "/v1/example/": {
                    "get": {
                        "operationId": "example",
                        "tags": ["MCP"],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        },
    )

    server = create_server(config)
    assert server is not None


def test_create_server_uses_backend_server_instructions(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        lambda *, base_url: {
            "openapi": "3.0.0",
            "info": {"title": "NoCFO", "version": "1.0.0"},
            "servers": [{"url": base_url}],
            X_NOCFO_MCP_SERVER_INSTRUCTIONS: "Start from bootstrap.",
            "paths": {
                "/v1/example/": {
                    "get": {
                        "operationId": "example",
                        "tags": ["MCP"],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        },
    )

    class DummyServer:
        pass

    captured_kwargs: dict[str, object] = {}

    def _fake_from_openapi(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return DummyServer()

    monkeypatch.setattr("fastmcp.FastMCP.from_openapi", _fake_from_openapi)

    server = create_server(config)
    assert isinstance(server, DummyServer)
    assert captured_kwargs["instructions"] == "Start from bootstrap."


def test_oauth_protected_resource_metadata_strips_trailing_slashes(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "NOCFO_MCP_AUTHORIZATION_SERVERS",
        "http://localhost:8000/",
    )
    monkeypatch.setenv(
        "NOCFO_MCP_JWKS_URI",
        "http://localhost:8000/.well-known/jwks.json",
    )
    monkeypatch.setenv("NOCFO_MCP_JWT_ISSUER", "http://localhost:8000")
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        lambda *, base_url: {
            "openapi": "3.0.0",
            "info": {"title": "NoCFO", "version": "1.0.0"},
            "servers": [{"url": base_url}],
            "paths": {},
        },
    )

    server = create_server(
        ToolkitConfig(base_url="http://localhost:8000"),
        options=MCPServerOptions(
            auth_mode="oauth",
            mcp_base_url="http://127.0.0.1:8002",
        ),
    )
    app = server.http_app(path="/mcp")
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    metadata = response.json()
    assert metadata["resource"] == "http://127.0.0.1:8002/mcp"
    assert metadata["authorization_servers"] == ["http://localhost:8000"]


def test_openapi_provider_maps_mcp_get_to_resources() -> None:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "NoCFO", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/v1/list/": {
                "get": {
                    "operationId": "bookkeeping.items.list",
                    "tags": ["MCP"],
                    X_MCP_NAMESPACE: "bookkeeping",
                    X_MCP_COMPONENT_TYPE: "resource",
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/v1/item/{id}/": {
                "get": {
                    "operationId": "bookkeeping.item.retrieve",
                    "tags": ["MCP"],
                    X_MCP_NAMESPACE: "bookkeeping",
                    X_MCP_COMPONENT_TYPE: "resource",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
            },
            "/v1/item/": {
                "post": {
                    "operationId": "bookkeeping.item.create",
                    "tags": ["MCP"],
                    X_MCP_NAMESPACE: "bookkeeping",
                    "x-mcp-required-permissions": ["bookkeeping_editor"],
                    "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }
    filtered = filter_mcp_spec(spec)
    client = httpx.AsyncClient(base_url="https://api.example.com")

    def _apply_component_mcp_metadata(route, component) -> None:
        apply_mcp_namespace_names(route, component)
        apply_mcp_operation_metadata(route, component)

    provider = OpenAPIProvider(
        openapi_spec=filtered,
        client=client,
        route_maps=MCP_OPENAPI_ROUTE_MAPS,
        mcp_component_fn=_apply_component_mcp_metadata,
        validate_output=True,
    )

    assert len(provider._tools) == 1
    create_tool = next(iter(provider._tools.values()))
    assert create_tool._route.operation_id == "bookkeeping.item.create"
    assert create_tool.name == "bookkeeping_item_create"
    assert create_tool.meta["nocfo"]["mcp"][X_MCP_NAMESPACE] == "bookkeeping"
    assert create_tool.meta["nocfo"]["mcp"]["x-mcp-required-permissions"] == [
        "bookkeeping_editor"
    ]
    assert len(provider._resources) == 2
    operation_ids = {
        resource._route.operation_id for resource in provider._resources.values()
    }
    assert "bookkeeping.items.list" in operation_ids
    assert "bookkeeping.item.retrieve" in operation_ids
    names = {resource.name for resource in provider._resources.values()}
    assert "bookkeeping_items_list" in names
    assert "bookkeeping_item_retrieve" in names
    first_resource = next(iter(provider._resources.values()))
    assert first_resource.meta["nocfo"]["mcp"][X_MCP_COMPONENT_TYPE] == "resource"
    assert len(provider._templates) == 0


def test_build_mcp_component_name_uses_x_mcp_namespace_extension() -> None:
    assert (
        build_mcp_component_name(
            "a.b.c",
            {X_MCP_NAMESPACE: "invoicing"},
        )
        == "invoicing_a_b_c"
    )


def test_build_mcp_component_name_normalizes_namespace_token() -> None:
    assert (
        build_mcp_component_name(
            "x.y",
            {X_MCP_NAMESPACE: "Balance Sheet"},
        )
        == "balance_sheet_x_y"
    )


def test_build_mcp_component_name_fallback_when_extension_missing() -> None:
    assert (
        build_mcp_component_name(
            "bookkeeping.item.create",
            {},
        )
        == "bookkeeping.item.create"
    )


def test_build_mcp_component_name_fallback_when_no_extensions() -> None:
    assert build_mcp_component_name("foo.bar", None) == "foo.bar"


def test_filter_mcp_spec_prefers_backend_component_type_extension() -> None:
    spec = {
        "paths": {
            "/v1/non-get-as-resource/": {
                "post": {
                    "operationId": "bookkeeping.custom.retrieve",
                    "tags": ["MCP"],
                    X_MCP_COMPONENT_TYPE: "resource",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        }
    }

    filtered = filter_mcp_spec(spec)
    tags = filtered["paths"]["/v1/non-get-as-resource/"]["post"]["tags"]
    assert "MCP_RESOURCE" in tags
    assert "MCP_TOOL" not in tags


def test_create_server_registers_invoice_app_tools(monkeypatch) -> None:
    config = ToolkitConfig(
        api_token="pat-token",
        token_source=TokenSource.ENV,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
    )
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.load_openapi_spec",
        lambda *, base_url: {
            "openapi": "3.0.0",
            "info": {"title": "NoCFO", "version": "1.0.0"},
            "servers": [{"url": base_url}],
            "paths": {
                "/v1/invoicing/{business_slug}/invoice/": {
                    "post": {
                        "operationId": "Sales Invoices - Create",
                        "tags": ["MCP"],
                        "parameters": [
                            {
                                "name": "business_slug",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "receiver": {"type": "integer"},
                                            "rows": {"type": "array"},
                                        },
                                        "required": ["receiver"],
                                    }
                                }
                            },
                        },
                        "responses": {"201": {"description": "OK"}},
                    }
                }
            },
        },
    )
    server = create_server(config)
    tools = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "invoice_create_form" in tools
    assert "invoice_create_submit" in tools


def test_build_form_defaults_applies_preset_values() -> None:
    defaults = _build_form_defaults(
        business_slug="demo-930bf1",
        preset={
            "receiver": 42,
            "invoicing_date": "2026-04-03",
            "payment_condition_days": 7,
            "rows": [{"name": "Consulting", "amount": 1500, "product_count": 2}],
        },
    )
    assert defaults["business_slug"] == "demo-930bf1"
    assert defaults["receiver"] == "42"
    assert defaults["row_name"] == "Consulting"
    assert defaults["row_amount"] == "1500"
    assert defaults["row_product_count"] == "2"
    assert defaults["product_id"] == ""
    assert "attachment_hints" in defaults
    assert defaults["preset_warnings"] == []


def test_build_invoice_payload_reports_row_errors() -> None:
    result = _build_invoice_payload(
        receiver="12",
        invoicing_date="2026-04-03",
        payment_condition_days="14",
        reference=None,
        description=None,
        contact_person=None,
        seller_reference=None,
        buyer_reference=None,
        row_name="",
        row_unit="kpl",
        row_amount="",
        row_product_count="1",
        row_vat_rate=None,
        row_vat_code=None,
        row_description=None,
        product_id=None,
        attachment_ids=None,
        extra_payload_json=None,
        invoice_payload=None,
        preset_payload=None,
    )
    assert result["errors"]
    assert "Either provide row fields" in result["errors"][0]


def test_build_non_ui_form_payload_includes_submit_tool() -> None:
    defaults = _build_form_defaults(
        business_slug="demo-930bf1",
        preset={"receiver": 12},
    )
    payload = _build_non_ui_form_payload(
        defaults=defaults,
        submit_tool_name="invoice_create_submit",
    )
    assert payload["mode"] == "fallback_form"
    assert payload["submit_tool"] == "invoice_create_submit"
    assert payload["prefill"]["business_slug"] == "demo-930bf1"
    assert payload["ui_supported"] is False
    assert "receiver_options" in payload
    assert "product_options" in payload
    assert "attachment_hints" in payload
    assert "agent_instructions" in payload
    assert "required_fields" in payload["agent_instructions"]
    required = set(payload["agent_instructions"]["required_fields"])
    assert {"receiver", "row_name", "row_amount"}.issubset(required)


def test_parse_tool_error_handles_json_payload() -> None:
    parsed = _parse_tool_error(
        '{"summary":"Invalid request","status_code":400,"field_errors":{"receiver":["required"]}}'
    )
    assert parsed["summary"] == "Invalid request"
    assert parsed["status_code"] == 400
    assert parsed["field_errors"]["receiver"] == ["required"]


def test_invoice_app_form_defaults_respects_preset() -> None:
    defaults = _build_form_defaults(
        business_slug="demo-930bf1",
        preset={
            "receiver": 77,
            "rows": [
                {
                    "name": "Consulting",
                    "amount": 1500.0,
                    "unit": "h",
                    "product_count": 10,
                }
            ],
        },
    )
    assert defaults["business_slug"] == "demo-930bf1"
    assert defaults["receiver"] == "77"
    assert defaults["row_name"] == "Consulting"
    assert defaults["row_amount"] == "1500.0"
    assert defaults["row_unit"] == "h"
    assert defaults["preset_warnings"] == []


def test_invoice_app_payload_builder_reports_invalid_inputs() -> None:
    result = _build_invoice_payload(
        receiver="not-an-int",
        invoicing_date="2026-01-01",
        payment_condition_days="14",
        reference=None,
        description=None,
        contact_person=None,
        seller_reference=None,
        buyer_reference=None,
        row_name="",
        row_unit="kpl",
        row_amount="abc",
        row_product_count="1",
        row_vat_rate=None,
        row_vat_code=None,
        row_description=None,
        product_id=None,
        attachment_ids=None,
        extra_payload_json='{"x": 1}',
        invoice_payload=None,
        preset_payload=None,
    )
    assert result["errors"]
    assert any("receiver" in issue for issue in result["errors"])
    assert any("row_amount" in issue for issue in result["errors"])


def test_invoice_app_non_ui_payload_shape() -> None:
    defaults = {
        "business_slug": "demo-930bf1",
        "receiver": "10",
        "invoicing_date": "2026-01-01",
        "payment_condition_days": "14",
        "reference": "",
        "description": "",
        "contact_person": "",
        "seller_reference": "",
        "buyer_reference": "",
        "row_name": "Service",
        "row_unit": "kpl",
        "row_amount": "100.00",
        "row_product_count": "1",
        "row_vat_rate": "",
        "row_vat_code": "",
        "row_description": "",
        "product_id": "",
        "attachment_ids": "",
        "extra_payload_json": "",
        "preset_payload": {},
        "receiver_options": [],
        "product_options": [],
        "unit_options": ["kpl"],
        "attachment_hints": "help",
        "preset_warnings": ["warning"],
    }
    payload = _build_non_ui_form_payload(
        defaults=defaults,
        submit_tool_name="invoice_create_submit",
    )
    assert payload["mode"] == "fallback_form"
    assert payload["ui_supported"] is False
    assert payload["submit_tool"] == "invoice_create_submit"
    assert payload["warnings"] == ["warning"]
    assert payload["prefill"]["receiver"] == "10"
    assert payload["attachment_hints"] == "help"


def test_build_invoice_payload_includes_vat_code() -> None:
    result = _build_invoice_payload(
        receiver="12",
        invoicing_date="2026-04-03",
        payment_condition_days="14",
        reference=None,
        description=None,
        contact_person=None,
        seller_reference=None,
        buyer_reference=None,
        row_name="Service line",
        row_unit="kpl",
        row_amount="100.00",
        row_product_count="1",
        row_vat_rate="25.5",
        row_vat_code="1",
        row_description=None,
        product_id="309",
        attachment_ids="12,34",
        extra_payload_json=None,
        invoice_payload=None,
        preset_payload=None,
    )
    assert result["errors"] == []
    rows = result["payload"]["rows"]
    assert isinstance(rows, list) and rows
    assert rows[0]["vat_code"] == 1
    assert rows[0]["product"] == 309
    assert result["payload"]["attachments"] == [12, 34]




def test_non_ui_form_fields_include_required_metadata() -> None:
    defaults = {
        "business_slug": "demo-930bf1",
        "receiver": "2289",
        "invoicing_date": "2026-01-01",
        "payment_condition_days": "14",
        "reference": "",
        "description": "",
        "contact_person": "",
        "seller_reference": "",
        "buyer_reference": "",
        "product_id": "",
        "row_name": "Service",
        "row_unit": "kpl",
        "row_amount": "100.00",
        "row_product_count": "1",
        "row_vat_rate": "",
        "row_vat_code": "1",
        "row_description": "",
        "attachment_ids": "",
        "extra_payload_json": "",
        "preset_payload": {},
        "receiver_options": [],
        "product_options": [],
        "unit_options": ["kpl"],
        "attachment_hints": "help",
        "preset_warnings": [],
    }
    payload = _build_non_ui_form_payload(
        defaults=defaults,
        submit_tool_name="invoice_create_submit",
    )
    assert payload["agent_instructions"]["required_fields"]
    fields = payload["fields"]
    receiver_field = next(field for field in fields if field["name"] == "receiver")
    assert receiver_field["required"] is True
    row_amount_field = next(field for field in fields if field["name"] == "row_amount")
    assert row_amount_field["required"] is True

def test_prefab_form_renders_selects_when_options_available() -> None:
    defaults = {
        "business_slug": "demo-930bf1",
        "receiver": "2289",
        "invoicing_date": "2026-01-01",
        "payment_condition_days": "14",
        "reference": "",
        "description": "",
        "contact_person": "",
        "seller_reference": "",
        "buyer_reference": "",
        "product_id": "309",
        "row_name": "Service",
        "row_unit": "kpl",
        "row_amount": "100.00",
        "row_product_count": "1",
        "row_vat_rate": "25.5",
        "row_vat_code": "1",
        "row_description": "",
        "attachment_ids": "",
        "extra_payload_json": "",
        "preset_payload": {},
        "receiver_options": [{"id": 2289, "label": "D Market Oy (BUSINESS)"}],
        "product_options": [{"id": 309, "label": "Siivous | unit=kpl"}],
        "unit_options": ["kpl", "h"],
        "attachment_hints": "Use file IDs.",
        "preset_warnings": [],
    }
    app = _build_prefab_form(defaults=defaults, submit_tool_name="invoice_create_submit")
    payload = app.to_json()
    payload_str = str(payload)
    assert "SelectOption" in payload_str
    assert "Advanced invoice options" in payload_str
    assert "attachment_ids" in payload_str


def test_invoice_app_parse_tool_error_handles_json_payload() -> None:
    parsed = _parse_tool_error(
        '{"summary":"Validation failed","status_code":400,'
        '"field_errors":{"receiver":["required"]}}'
    )
    assert parsed["summary"] == "Validation failed"
    assert parsed["status_code"] == 400
    assert parsed["field_errors"] == {"receiver": ["required"]}
