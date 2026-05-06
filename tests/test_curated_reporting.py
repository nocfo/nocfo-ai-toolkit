from __future__ import annotations

import asyncio
from unittest.mock import patch

from nocfo_toolkit.mcp.curated.reporting.report import run_report
from nocfo_toolkit.mcp.curated.schemas import (
    BalanceSheetReportInput,
    IncomeStatementReportInput,
)


def test_run_report_accepts_string_report_type() -> None:
    captured: dict[str, object] = {}

    async def _request(
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: dict[str, object] | None = None,
        business_slug: str | None = None,
    ) -> dict[str, object]:
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        captured["json_body"] = json_body
        captured["business_slug"] = business_slug
        return {"labels": [], "rows": []}

    class _FakeClient:
        async def request(self, *args, **kwargs):
            return await _request(*args, **kwargs)

    async def _run() -> None:
        params = BalanceSheetReportInput.model_validate(
            {
                "business": "demo",
                "columns": [{"date_at": "2025-12-31"}],
            }
        )
        with (
            patch(
                "nocfo_toolkit.mcp.curated.reporting.report.business_slug",
                return_value="demo",
            ),
            patch(
                "nocfo_toolkit.mcp.curated.reporting.report.get_client",
                return_value=_FakeClient(),
            ),
        ):
            result = await run_report("balance-sheet", params)
        assert result["report_type"] == "balance-sheet"
        assert result["business"] == "demo"

    asyncio.run(_run())
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/business/demo/report/balance-sheet/"
    assert captured["business_slug"] == "demo"


def test_run_report_sends_explicit_report_columns() -> None:
    captured: dict[str, object] = {}

    async def _request(
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: dict[str, object] | None = None,
        business_slug: str | None = None,
    ) -> dict[str, object]:
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        captured["json_body"] = json_body
        captured["business_slug"] = business_slug
        return {
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "rows": [{"name": "Revenue", "values": [1, 2, 3, 4]}],
        }

    class _FakeClient:
        async def request(self, *args, **kwargs):
            return await _request(*args, **kwargs)

    async def _run() -> None:
        params = IncomeStatementReportInput.model_validate(
            {
                "business": "demo",
                "columns": [
                    {
                        "name": "Q1",
                        "date_from": "2026-01-01",
                        "date_to": "2026-03-31",
                    },
                    {
                        "name": "Q2",
                        "date_from": "2026-04-01",
                        "date_to": "2026-06-30",
                    },
                    {
                        "name": "Q3",
                        "date_from": "2026-07-01",
                        "date_to": "2026-09-30",
                    },
                    {
                        "name": "Q4",
                        "date_from": "2026-10-01",
                        "date_to": "2026-12-31",
                    },
                ],
            }
        )
        with (
            patch(
                "nocfo_toolkit.mcp.curated.reporting.report.business_slug",
                return_value="demo",
            ),
            patch(
                "nocfo_toolkit.mcp.curated.reporting.report.get_client",
                return_value=_FakeClient(),
            ),
        ):
            result = await run_report("income-statement", params)
        assert result["data"]["labels"] == ["Q1", "Q2", "Q3", "Q4"]
        assert result["data"]["rows"][0]["values"] == [1, 2, 3, 4]

    asyncio.run(_run())
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/business/demo/report/income-statement/"
    assert captured["business_slug"] == "demo"
    assert captured["json_body"] == {
        "columns": [
            {"name": "Q1", "date_from": "2026-01-01", "date_to": "2026-03-31"},
            {"name": "Q2", "date_from": "2026-04-01", "date_to": "2026-06-30"},
            {"name": "Q3", "date_from": "2026-07-01", "date_to": "2026-09-30"},
            {"name": "Q4", "date_from": "2026-10-01", "date_to": "2026-12-31"},
        ],
        "extend_accounts": False,
        "append_comparison_columns": False,
    }
