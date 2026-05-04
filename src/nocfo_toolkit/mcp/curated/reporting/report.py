"""Reporting and period MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from nocfo_toolkit.mcp.curated.confirmation import confirm_mutation
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BalanceSheetReportInput,
    BusinessPaginationInput,
    DeletedResponse,
    EquityChangesReportInput,
    IdentifierInput,
    IdentifierPayloadInput,
    IncomeStatementReportInput,
    JournalReportInput,
    LedgerReportInput,
    ListEnvelope,
    PeriodListItem,
    PeriodSummary,
    ReportResponse,
    VatReportInput,
    dump_model,
    dump_model_from_backend,
)
from nocfo_toolkit.mcp.curated.utils import report_body


@tool(
    name="reporting_accounting_periods_list",
    description="List accounting periods for the selected business.",
    output_schema=ListEnvelope[PeriodListItem].model_json_schema(),
)
async def reporting_accounting_periods_list(
    params: BusinessPaginationInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/business/{slug}/period/",
        params={"search": args.query},
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=PeriodListItem,
    )


@tool(
    name="reporting_accounting_period_retrieve",
    description=(
        "Retrieve one accounting period by period ID from the accounting periods list."
    ),
)
async def reporting_accounting_period_retrieve(
    params: IdentifierInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    period_id = get_client().require_numeric_identifier(
        args.identifier, field_name="period_id"
    )
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/period/{period_id}/",
        business_slug=slug,
    )
    return dump_model_from_backend(PeriodSummary, result)


@tool(
    name="reporting_accounting_period_update",
    description=(
        "Update one accounting period by period ID from the accounting periods list. "
        "This can fail when posted data protects the period."
    ),
)
async def reporting_accounting_period_update(
    params: IdentifierPayloadInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    period_id = get_client().require_numeric_identifier(
        args.identifier, field_name="period_id"
    )
    path = f"/v1/business/{slug}/period/{period_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="reporting_accounting_period_update",
        target_resource={"type": "accounting_period", "id": str(period_id)},
        parameters=args.payload,
    )
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(PeriodSummary, result)


@tool(
    name="reporting_accounting_period_delete",
    description="Delete one accounting period by period ID from the accounting periods list.",
)
async def reporting_accounting_period_delete(
    params: IdentifierInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    period_id = get_client().require_numeric_identifier(
        args.identifier, field_name="period_id"
    )
    path = f"/v1/business/{slug}/period/{period_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="reporting_accounting_period_delete",
        target_resource={"type": "accounting_period", "id": str(period_id)},
    )
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(id=period_id))


@tool(
    name="reporting_vat_periods_list",
    description="List VAT periods for the selected business.",
    output_schema=ListEnvelope[PeriodListItem].model_json_schema(),
)
async def reporting_vat_periods_list(
    params: BusinessPaginationInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    return await get_client().list_page(
        f"/v1/business/{slug}/vat_period/",
        params={"search": args.query},
        cursor=args.cursor,
        limit=args.limit,
        business_slug=slug,
        item_model=PeriodListItem,
    )


@tool(
    name="reporting_vat_period_retrieve",
    description="Retrieve one VAT period by VAT period ID from the VAT periods list.",
)
async def reporting_vat_period_retrieve(params: IdentifierInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    vat_period_id = get_client().require_numeric_identifier(
        args.identifier, field_name="vat_period_id"
    )
    result = await get_client().request(
        "GET",
        f"/v1/business/{slug}/vat_period/{vat_period_id}/",
        business_slug=slug,
    )
    return dump_model_from_backend(PeriodSummary, result)


@tool(
    name="reporting_vat_period_update",
    description=(
        "Update one VAT period by VAT period ID from the VAT periods list. "
        "The period must be editable and not reported."
    ),
)
async def reporting_vat_period_update(
    params: IdentifierPayloadInput,
) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    vat_period_id = get_client().require_numeric_identifier(
        args.identifier, field_name="vat_period_id"
    )
    path = f"/v1/business/{slug}/vat_period/{vat_period_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="reporting_vat_period_update",
        target_resource={"type": "vat_period", "id": str(vat_period_id)},
        parameters=args.payload,
    )
    result = await get_client().request(
        "PATCH",
        path,
        json_body=args.payload,
        business_slug=slug,
    )
    return dump_model_from_backend(PeriodSummary, result)


@tool(
    name="reporting_vat_period_delete",
    description=(
        "Delete one VAT period by VAT period ID from the VAT periods list. "
        "This can fail when linked records prevent deletion."
    ),
)
async def reporting_vat_period_delete(params: IdentifierInput) -> dict[str, Any]:
    args = params
    slug = await business_slug(args.business)
    vat_period_id = get_client().require_numeric_identifier(
        args.identifier, field_name="vat_period_id"
    )
    path = f"/v1/business/{slug}/vat_period/{vat_period_id}/"
    await confirm_mutation(
        business=slug,
        tool_name="reporting_vat_period_delete",
        target_resource={"type": "vat_period", "id": str(vat_period_id)},
    )
    await get_client().request(
        "DELETE",
        path,
        business_slug=slug,
    )
    return dump_model(DeletedResponse(id=vat_period_id))


async def run_report(report_type: str, report: Any) -> dict[str, Any]:
    slug = await business_slug(report.business)
    tag_ids = None
    if report.tag_names:
        tag_ids = [
            await get_client().resolve_id(
                f"/v1/business/{slug}/tags/",
                lookup_field="name",
                lookup_value=name,
                search_param="search",
                business_slug=slug,
            )
            for name in report.tag_names
        ]
    result = await get_client().request(
        "POST",
        f"/v1/business/{slug}/report/{report_type}/",
        json_body=report_body(report, tag_ids=tag_ids),
        business_slug=slug,
    )
    return dump_model(
        ReportResponse(
            report_type=report_type,
            business=slug,
            data=result,
            next_action_hint=(
                "Full report data is returned. "
                "Use narrower dates or tag filters to reduce payload size."
            ),
        )
    )


@tool(
    name="reporting_balance_sheet_retrieve",
    description="Generate balance sheet report data.",
)
async def reporting_balance_sheet_retrieve(
    params: BalanceSheetReportInput,
) -> dict[str, Any]:
    return await run_report("balance-sheet", params)


@tool(
    name="reporting_equity_changes_retrieve",
    description="Generate equity changes report data.",
)
async def reporting_equity_changes_retrieve(
    params: EquityChangesReportInput,
) -> dict[str, Any]:
    return await run_report("equity-changes", params)


@tool(
    name="reporting_income_statement_retrieve",
    description="Generate income statement report data.",
)
async def reporting_income_statement_retrieve(
    params: IncomeStatementReportInput,
) -> dict[str, Any]:
    return await run_report("income-statement", params)


@tool(
    name="reporting_journal_retrieve",
    description="Generate journal report data.",
)
async def reporting_journal_retrieve(params: JournalReportInput) -> dict[str, Any]:
    return await run_report("journal", params)


@tool(
    name="reporting_ledger_retrieve",
    description="Generate ledger report data.",
)
async def reporting_ledger_retrieve(params: LedgerReportInput) -> dict[str, Any]:
    return await run_report("ledger", params)


@tool(
    name="reporting_vat_retrieve",
    description="Generate VAT statement data.",
)
async def reporting_vat_retrieve(params: VatReportInput) -> dict[str, Any]:
    return await run_report("vat-report", params)
