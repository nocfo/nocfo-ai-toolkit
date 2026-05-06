from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from starlette.testclient import TestClient

from nocfo_toolkit.config import OutputFormat, TokenSource, ToolkitConfig
from nocfo_toolkit.mcp.curated import CuratedNocfoClient
from nocfo_toolkit.mcp.curated.schemas import (
    AccountListItem,
    AccountSummary,
    ContactListItem,
    DocumentDetail,
    DocumentListItem,
    DocumentSummary,
    EntrySummary,
    ProductSummary,
    PurchaseInvoiceListItem,
    PurchaseInvoiceSummary,
    RelationSummary,
    SalesInvoiceListItem,
    SalesInvoiceSummary,
)
from nocfo_toolkit.mcp.curated.utils import decode_tool_handle
from nocfo_toolkit.mcp.server import (
    MCP_CLIENT_HEADER,
    MCP_DEFAULT_CLIENT,
    MCP_RUNTIME_CONTRACT_HEADER,
    MCP_RUNTIME_CONTRACT_VALUE,
    _inject_mcp_runtime_contract_header,
    _inject_mcp_client_header,
    _request_requires_mcp_runtime_contract_header,
    create_server,
    MCPServerOptions,
    run_http_server,
)


def _jwt_with_payload(payload: dict[str, object]) -> str:
    raw = json.dumps(payload).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


def test_runtime_contract_header_is_added_for_regular_v1_mcp_operations() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/user/")

    asyncio.run(_inject_mcp_runtime_contract_header(request))

    assert request.headers[MCP_RUNTIME_CONTRACT_HEADER] == MCP_RUNTIME_CONTRACT_VALUE


def test_runtime_contract_header_is_not_added_for_v1_mcp_paths() -> None:
    request = httpx.Request(
        "GET", "https://api.example.com/v1/mcp/business/demo/accounts/"
    )

    asyncio.run(_inject_mcp_runtime_contract_header(request))

    assert MCP_RUNTIME_CONTRACT_HEADER not in request.headers


def test_runtime_contract_header_requirement_uses_path_shape_only() -> None:
    assert _request_requires_mcp_runtime_contract_header(
        httpx.Request("GET", "https://api.example.com/v1/user/")
    )
    assert not _request_requires_mcp_runtime_contract_header(
        httpx.Request("GET", "https://api.example.com/v1/mcp/business/demo/accounts/")
    )


def test_x_nocfo_client_header_defaults_to_nocfo_mcp(monkeypatch) -> None:
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.get_http_headers",
        lambda include=None: {},
    )
    request = httpx.Request("GET", "https://api.example.com/v1/business/")

    asyncio.run(
        _inject_mcp_client_header(
            request,
            default_client=MCP_DEFAULT_CLIENT,
        )
    )

    assert request.headers[MCP_CLIENT_HEADER] == "nocfo-mcp"


def test_x_nocfo_client_header_passes_through_incoming_header(monkeypatch) -> None:
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.get_http_headers",
        lambda include=None: {"x-nocfo-client": "custom-agent/1.0"},
    )
    request = httpx.Request("GET", "https://api.example.com/v1/business/")

    asyncio.run(
        _inject_mcp_client_header(
            request,
            default_client=MCP_DEFAULT_CLIENT,
        )
    )

    assert request.headers[MCP_CLIENT_HEADER] == "custom-agent/1.0"


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

    server = create_server(config)
    assert server is not None


def test_create_server_uses_curated_server_instructions() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )

    server = create_server(config)

    assert 'business="current"' in server.instructions
    assert "blueprint" in server.instructions
    assert "entries" in server.instructions


def test_create_server_registers_curated_tool_surface() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    names = {tool.name for tool in tools}

    assert "common_current_business_retrieve" in names
    assert "bookkeeping_accounts_list" in names
    assert "bookkeeping_accounts_search" not in names
    assert "bookkeeping_document_create" in names
    assert "bookkeeping_documents_search" not in names
    assert "bookkeeping_entries_list" in names
    assert "bookkeeping_document_relation_update" not in names
    assert "invoicing_contacts_search" not in names
    assert "invoicing_sales_invoices_search" not in names
    assert "invoicing_purchase_invoices_search" not in names
    assert "invoicing_sales_invoice_action" in names
    assert "common_user_update" not in names
    assert "reporting_report_retrieve" not in names
    assert "reporting_balance_sheet_retrieve" in names
    assert "reporting_equity_changes_retrieve" in names
    assert "reporting_income_statement_retrieve" in names
    assert "reporting_journal_retrieve" in names
    assert "reporting_ledger_retrieve" in names
    assert "reporting_vat_retrieve" in names
    assert "constants_retrieve" in names
    assert "constants_vat_codes_retrieve" not in names
    assert "constants_vat_rates_retrieve" not in names
    assert "docs_retrieve" in names
    assert "docs_blueprint" not in names
    assert "docs_glossary" not in names
    assert "docs_bootstrap" not in names
    assert "constants_permissions_retrieve" not in names


def test_curated_tools_use_pydantic_params_argument() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    by_name = {tool.name: tool for tool in tools}

    document_list_schema = by_name["bookkeeping_documents_list"].parameters
    assert set(document_list_schema["properties"]) == {"params"}
    assert "DocumentListInput" in document_list_schema["$defs"]

    invoice_action_schema = by_name["invoicing_sales_invoice_action"].parameters
    assert set(invoice_action_schema["properties"]) == {"params"}
    assert "SalesInvoiceActionInput" in invoice_action_schema["$defs"]

    document_create_schema = by_name["bookkeeping_document_create"].parameters
    assert "DocumentMutationInput" in document_create_schema["$defs"]
    payload_schema = document_create_schema["$defs"]["DocumentCreatePayload"]
    assert "blueprint" in payload_schema["required"]
    assert "tag_ids" not in payload_schema.get("required", [])


def test_number_lookup_resources_do_not_expose_internal_ids() -> None:
    for model in (
        AccountSummary,
        DocumentSummary,
        SalesInvoiceSummary,
        PurchaseInvoiceSummary,
    ):
        assert "id" not in model.model_fields

    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    by_name = {tool.name: tool for tool in tools}

    invoice_action_schema = by_name["invoicing_sales_invoice_action"].parameters
    sales_action_fields = invoice_action_schema["$defs"]["SalesInvoiceActionInput"][
        "properties"
    ]
    assert "invoice_number" in sales_action_fields
    assert "invoice_id" not in sales_action_fields

    for tool_name, schema_name, forbidden in (
        ("bookkeeping_account_retrieve", "AccountRetrieveInput", "account_id"),
        ("bookkeeping_document_retrieve", "DocumentRetrieveInput", "document_id"),
        ("invoicing_sales_invoice_retrieve", "InvoiceRetrieveInput", "invoice_id"),
        ("invoicing_purchase_invoice_retrieve", "InvoiceRetrieveInput", "invoice_id"),
    ):
        retrieve_schema = by_name[tool_name].parameters
        retrieve_fields = retrieve_schema["$defs"][schema_name]["properties"]
        assert list(retrieve_fields) == ["business", "tool_handle"]
        assert forbidden not in retrieve_fields


def test_tool_handle_descriptions_instruct_copy_and_pass_unchanged() -> None:
    assert (
        "items[].tool_handle" in AccountListItem.model_fields["tool_handle"].description
    )
    assert (
        "pass it unchanged" in AccountListItem.model_fields["tool_handle"].description
    )
    assert (
        "bookkeeping_accounts_list.items[].tool_handle"
        in AccountSummary.model_fields["tool_handle"].description
    )
    assert (
        "bookkeeping_documents_list.items[].tool_handle"
        in DocumentSummary.model_fields["tool_handle"].description
    )
    assert (
        "invoicing_sales_invoices_list.items[].tool_handle"
        in SalesInvoiceSummary.model_fields["tool_handle"].description
    )
    assert (
        "invoicing_purchase_invoices_list.items[].tool_handle"
        in PurchaseInvoiceSummary.model_fields["tool_handle"].description
    )

    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)
    tools = asyncio.run(server.list_tools(run_middleware=False))
    by_name = {tool.name: tool for tool in tools}
    fields = by_name["bookkeeping_account_retrieve"].parameters["$defs"][
        "AccountRetrieveInput"
    ]["properties"]
    assert (
        "bookkeeping_accounts_list.items[].tool_handle"
        in fields["tool_handle"]["description"]
    )
    assert "Pass it unchanged" in fields["tool_handle"]["description"]


def test_vat_and_blueprint_fields_point_to_constants_and_docs_tools() -> None:
    assert (
        "constants_retrieve with kind=vat_codes"
        in AccountSummary.model_fields["default_vat_code"].description
    )
    assert (
        "constants_retrieve with kind=vat_rates"
        in AccountSummary.model_fields["default_vat_rate"].description
    )
    assert (
        "docs_retrieve with kind=blueprint"
        in DocumentDetail.model_fields["blueprint"].description
    )
    assert (
        "constants_retrieve with kind=vat_codes"
        in EntrySummary.model_fields["vat_code"].description
    )
    assert (
        "constants_retrieve with kind=vat_rates"
        in EntrySummary.model_fields["vat_rate"].description
    )
    assert (
        "constants_retrieve with kind=vat_codes"
        in ProductSummary.model_fields["vat_code"].description
    )
    assert (
        "constants_retrieve with kind=vat_rates"
        in ProductSummary.model_fields["vat_rate"].description
    )


def test_relation_fields_expose_handles_for_cross_resource_followups() -> None:
    assert "contact_id" in DocumentSummary.model_fields
    assert "receiver_id" in SalesInvoiceSummary.model_fields
    assert "document_handle" in PurchaseInvoiceSummary.model_fields
    assert "related_document_handle" in RelationSummary.model_fields
    assert "tool_handle" in DocumentSummary.model_fields
    assert "tool_handle" in SalesInvoiceSummary.model_fields

    assert "receiver" not in SalesInvoiceSummary.model_fields
    assert "document" not in PurchaseInvoiceSummary.model_fields
    assert "related_document" not in RelationSummary.model_fields


def test_list_models_remain_compact_without_nested_workflow_objects() -> None:
    assert "workflow" not in DocumentListItem.model_fields
    assert "suggestion_info" not in DocumentListItem.model_fields
    assert "available_actions" not in DocumentListItem.model_fields
    assert "rows" not in SalesInvoiceListItem.model_fields
    assert "receiver_info" not in SalesInvoiceListItem.model_fields
    assert "invoicing_einvoice_operator" not in ContactListItem.model_fields
    assert "header_path" not in AccountListItem.model_fields
    assert "default_vat_code" not in AccountListItem.model_fields
    assert "default_vat_rate" not in AccountListItem.model_fields
    assert "sender_bank_account" not in PurchaseInvoiceListItem.model_fields


def test_sales_invoice_workflow_next_action_prefers_accept_then_send() -> None:
    unaccepted = SalesInvoiceListItem.model_validate(
        {"id": 1, "invoice_number": "1001", "status": "DRAFT", "is_sendable": False}
    )
    assert unaccepted.next_action == "accept"
    assert "action=accept" in (unaccepted.next_action_hint or "")

    accepted_not_sent = SalesInvoiceListItem.model_validate(
        {
            "id": 2,
            "invoice_number": "1002",
            "status": "ACCEPTED",
            "is_sendable": True,
            "last_delivery_at": None,
        }
    )
    assert accepted_not_sent.next_action == "send"
    assert "invoicing_sales_invoice_send" in (accepted_not_sent.next_action_hint or "")

    paid = SalesInvoiceListItem.model_validate(
        {"id": 3, "invoice_number": "1003", "status": "PAID", "is_sendable": False}
    )
    assert paid.next_action is None


def test_unknown_enum_value_passes_through_as_string() -> None:
    item = SalesInvoiceListItem.model_validate(
        {"id": 4, "invoice_number": "1004", "status": "PARTIALLY_PAID"}
    )
    assert item.status == "PARTIALLY_PAID"


def test_pagination_default_limit_is_10() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)
    tools = asyncio.run(server.list_tools(run_middleware=False))
    by_name = {tool.name: tool for tool in tools}
    account_list_fields = by_name["bookkeeping_accounts_list"].parameters["$defs"][
        "AccountListInput"
    ]["properties"]
    assert account_list_fields["limit"]["default"] == 10


def test_contact_retrieve_uses_exact_selector_fields() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    contact_retrieve = {tool.name: tool for tool in tools}["invoicing_contact_retrieve"]

    fields = contact_retrieve.parameters["$defs"]["ContactRetrieveInput"]["properties"]
    assert "contact_id" in fields
    assert "tool_handle" in fields
    assert "contact_business_id" not in fields


def test_contact_list_exposes_paginated_lookup_fields() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    contact_list = {tool.name: tool for tool in tools}["invoicing_contacts_list"]

    fields = contact_list.parameters["$defs"]["ContactListInput"]["properties"]
    assert "limit" in fields
    assert "cursor" in fields
    assert "query" in fields
    assert "contact_business_id" in fields


def test_constants_retrieve_uses_kind_switch_input() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    constants_tool = {tool.name: tool for tool in tools}["constants_retrieve"]

    fields = constants_tool.parameters["$defs"]["ConstantsRetrieveInput"]["properties"]
    assert "kind" in fields
    assert "date_at" in fields


def test_docs_retrieve_uses_kind_switch_input() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    docs_tool = {tool.name: tool for tool in tools}["docs_retrieve"]

    fields = docs_tool.parameters["$defs"]["DocsRetrieveInput"]["properties"]
    assert "kind" in fields


def test_reporting_tools_use_report_specific_input_schemas() -> None:
    config = ToolkitConfig(
        api_token=None,
        token_source=TokenSource.MISSING,
        base_url="https://api-prd.nocfo.io",
        output_format=OutputFormat.TABLE,
        jwt_token="jwt-only-token",
    )
    server = create_server(config)

    tools = asyncio.run(server.list_tools(run_middleware=False))
    tools_by_name = {tool.name: tool for tool in tools}
    balance_sheet_tool = tools_by_name["reporting_balance_sheet_retrieve"]
    income_statement_tool = tools_by_name["reporting_income_statement_retrieve"]

    assert "BalanceSheetReportInput" in balance_sheet_tool.parameters["$defs"]
    balance_sheet_fields = balance_sheet_tool.parameters["$defs"][
        "BalanceSheetReportInput"
    ]["properties"]
    balance_sheet_column_ref = balance_sheet_fields["columns"]["items"]["$ref"]
    assert balance_sheet_column_ref.endswith("/PointInTimeReportColumnInput")

    assert "IncomeStatementReportInput" in income_statement_tool.parameters["$defs"]
    income_statement_fields = income_statement_tool.parameters["$defs"][
        "IncomeStatementReportInput"
    ]["properties"]
    income_statement_column_ref = income_statement_fields["columns"]["items"]["$ref"]
    assert income_statement_column_ref.endswith("/DateRangeReportColumnInput")


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


def test_current_business_resolves_from_jwt_claim() -> None:
    token = _jwt_with_payload({"business_slug": "demo"})
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com"),
        ToolkitConfig(base_url="https://api.example.com", jwt_token=token),
    )

    result = asyncio.run(client.resolve_business("current"))

    assert result.slug == "demo"
    assert result.source == "jwt"


def test_current_business_resolves_from_prefixed_jwt_claim() -> None:
    token = _jwt_with_payload({"business_slug": "demo"})
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com"),
        ToolkitConfig(base_url="https://api.example.com", jwt_token=f"Token {token}"),
    )

    result = asyncio.run(client.resolve_business("current"))

    assert result.slug == "demo"
    assert result.source == "jwt"


def test_current_business_ignores_literal_current_in_jwt_claim() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/business/"
        return httpx.Response(
            200,
            json={"results": [{"slug": "demo", "name": "Demo Oy", "form_name": "Oy"}]},
        )

    token = _jwt_with_payload({"business_slug": "current"})
    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token=token),
    )

    result = asyncio.run(client.resolve_business("current"))

    assert result.slug == "demo"
    assert result.source == "single_accessible_business"


def test_current_business_ignores_nonstandard_jwt_business_claims() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/business/"
        return httpx.Response(
            200,
            json={"results": [{"slug": "demo", "name": "Demo Oy", "form_name": "Oy"}]},
        )

    token = _jwt_with_payload({"business": {"slug": "nested-demo"}})
    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token=token),
    )

    result = asyncio.run(client.resolve_business("current"))

    assert result.slug == "demo"
    assert result.source == "single_accessible_business"


def test_current_business_resolves_single_accessible_business() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/business/"
        return httpx.Response(
            200,
            json={"results": [{"slug": "demo", "name": "Demo Oy", "form_name": "Oy"}]},
        )

    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token=None),
    )

    result = asyncio.run(client.resolve_business("current"))

    assert result.slug == "demo"
    assert result.name == "Demo Oy"
    assert result.source == "single_accessible_business"


def test_list_page_uses_linear_style_cursor_envelope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "number": 1910, "name": "Bank", "extra": "x"}
                    ],
                    "size": 2,
                    "next": "https://api.example.com/next",
                },
            )
        return httpx.Response(200, json={"results": [{"id": 2, "number": 3000}]})

    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token="token"),
    )

    first = asyncio.run(
        client.list_page("/v1/business/demo/account/", limit=1, fields=("id", "number"))
    )
    second = asyncio.run(
        client.list_page(
            "/v1/business/demo/account/",
            limit=1,
            cursor=first["page_info"]["next_cursor"],
            fields=("id", "number"),
        )
    )

    assert first["items"] == [{"id": 1, "number": 1910}]
    assert first["page_info"]["has_next_page"] is True
    assert first["page_info"]["total_size"] == 2
    assert "page_info.total_size" in (first.get("usage_hint") or "")
    assert second["items"] == [{"id": 2, "number": 3000}]
    assert requests[1].url.params.get("page") == "2"


def test_retrieve_by_lookup_search_param_requires_exact_field_match() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/business/demo/contacts/":
            assert request.url.params.get("search") == "CUST-1"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "contact_business_id": "CUST-10", "name": "Wrong"},
                        {"id": 2, "contact_business_id": "CUST-1", "name": "Right"},
                    ]
                },
            )
        assert request.url.path == "/v1/business/demo/contacts/2/"
        return httpx.Response(
            200,
            json={"id": 2, "contact_business_id": "CUST-1", "name": "Right"},
        )

    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token="token"),
    )

    result = asyncio.run(
        client.retrieve_by_lookup(
            "/v1/business/demo/contacts/",
            "/v1/business/demo/contacts/{id}/",
            lookup_field="contact_business_id",
            lookup_value="CUST-1",
            search_param="search",
            business_slug="demo",
            fields=("id", "contact_business_id", "name"),
        )
    )

    assert result == {"id": 2, "contact_business_id": "CUST-1", "name": "Right"}
    assert len(requests) == 2


def test_resolve_exact_id_accepts_only_handle_or_id() -> None:
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com"),
        ToolkitConfig(base_url="https://api.example.com", jwt_token="token"),
    )

    with pytest.raises(Exception):
        asyncio.run(
            client.resolve_exact_id(
                tool_handle=None,
                internal_id=None,
                expected_resource="bookkeeping_document",
                id_field_name="document_id",
            )
        )

    with pytest.raises(Exception):
        asyncio.run(
            client.resolve_exact_id(
                tool_handle=base64.urlsafe_b64encode(
                    b'{"resource":"bookkeeping_document","id":7}'
                ).decode("ascii"),
                internal_id=7,
                expected_resource="bookkeeping_document",
                id_field_name="document_id",
            )
        )

    resolved = asyncio.run(
        client.resolve_exact_id(
            tool_handle=base64.urlsafe_b64encode(
                b'{"resource":"bookkeeping_document","id":7}'
            ).decode("ascii"),
            internal_id=None,
            expected_resource="bookkeeping_document",
            id_field_name="document_id",
        )
    )
    assert resolved == 7


def test_decode_tool_handle_rejects_non_positive_ids() -> None:
    handle = base64.urlsafe_b64encode(
        b'{"resource":"bookkeeping_document","id":0}'
    ).decode("ascii")

    with pytest.raises(Exception) as exc_info:
        decode_tool_handle(handle, expected_resource="bookkeeping_document")

    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "invalid_reference"


def test_require_numeric_identifier_returns_structured_invalid_request() -> None:
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com"),
        ToolkitConfig(base_url="https://api.example.com", jwt_token="token"),
    )

    with pytest.raises(Exception) as exc_info:
        client.require_numeric_identifier("period-x", field_name="period_id")
    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "invalid_request"
    assert "period_id" in payload["message"]

    with pytest.raises(Exception) as exc_info:
        client.require_numeric_identifier("0", field_name="period_id")
    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "invalid_request"


def test_resolve_id_ambiguity_returns_handle_oriented_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/business/demo/account/"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"id": 10, "number": 1910, "name": "Bank EUR"},
                    {"id": 11, "number": 1910, "name": "Bank USD"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token="token"),
    )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            client.resolve_id(
                "/v1/business/demo/account/",
                lookup_field="number",
                lookup_value=1910,
                business_slug="demo",
            )
        )

    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "ambiguous_reference"
    assert "items[].tool_handle" in payload["hint"]
    assert "tool_handle" in payload["candidates"][0]
    assert "id" not in payload["candidates"][0]


def test_permission_error_is_enriched_with_current_permissions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/business/demo/me/permissions/":
            return httpx.Response(
                200,
                json={"granted_permission_ids": ["view_bookkeeping"]},
            )
        return httpx.Response(403, json={"detail": "Forbidden"})

    transport = httpx.MockTransport(handler)
    client = CuratedNocfoClient(
        httpx.AsyncClient(base_url="https://api.example.com", transport=transport),
        ToolkitConfig(base_url="https://api.example.com", jwt_token="token"),
    )

    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            client.request(
                "POST",
                "/v1/business/demo/document/",
                json_body={},
                business_slug="demo",
            )
        )

    payload = json.loads(str(exc_info.value))
    assert payload["error_type"] == "permission_denied"
    assert payload["current_permissions"] == ["view_bookkeeping"]


def test_run_http_server_forwards_stateless_http(monkeypatch) -> None:
    config = ToolkitConfig(base_url="http://localhost:8000")

    class DummyServer:
        def run(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

    captured_kwargs: dict[str, object] = {}
    monkeypatch.setattr(
        "nocfo_toolkit.mcp.server.create_server",
        lambda config, options=None: DummyServer(),
    )

    run_http_server(
        config,
        host="127.0.0.1",
        port=9000,
        path="/mcp",
        options=MCPServerOptions(stateless_http=True),
    )

    assert captured_kwargs["transport"] == "http"
    assert captured_kwargs["host"] == "127.0.0.1"
    assert captured_kwargs["port"] == 9000
    assert captured_kwargs["path"] == "/mcp"
    assert captured_kwargs["stateless_http"] is True
