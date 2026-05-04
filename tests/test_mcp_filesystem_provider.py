from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers import FileSystemProvider

from nocfo_toolkit.config import ToolkitConfig
from nocfo_toolkit.mcp.server import MCPServerOptions, create_server


def test_filesystem_provider_discovers_curated_tools() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "nocfo_toolkit"
        / "mcp"
        / "curated"
    )
    server = FastMCP("NoCFO-test", providers=[FileSystemProvider(root=root)])
    tools = asyncio.run(server.list_tools(run_middleware=False))
    names = {tool.name for tool in tools}
    assert "bookkeeping_accounts_list" in names
    assert "invoicing_sales_invoice_create" in names
    assert "reporting_income_statement_retrieve" in names


def test_create_server_registers_curated_tools_via_filesystem_provider() -> None:
    server = create_server(
        ToolkitConfig(base_url="https://api-prd.nocfo.io", jwt_token="jwt-only-token"),
        options=MCPServerOptions(tool_search=False),
    )
    tools = asyncio.run(server.list_tools(run_middleware=False))
    names = {tool.name for tool in tools}
    assert "bookkeeping_accounts_list" in names
    assert "invoicing_sales_invoice_create" in names
    assert "constants_retrieve" in names
