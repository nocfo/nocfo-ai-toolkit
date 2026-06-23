"""Reporting and period MCP tools."""

from __future__ import annotations

from typing import Any

from fastmcp.tools import tool
from fastmcp.tools.tool import ToolAnnotations
from nocfo_toolkit.mcp.curated.batch import run_batch
from nocfo_toolkit.mcp.curated.runtime import business_slug, get_client
from nocfo_toolkit.mcp.curated.schemas import (
    BalanceSheetReportInput,
    BatchResponse,
    BusinessPaginationInput,
    DeletedResponse,
    EquityChangesReportInput,
    IdentifierInput,
    IdentifiersInput,
    IdentifiersPayloadInput,
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
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
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
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
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
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Update one or more accounting periods selected by identifiers (period IDs); the same payload "
        "is applied to every period. Batch all targets into one call. Can fail per period when posted data protects it."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def reporting_accounting_period_update(
    params: IdentifiersPayloadInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(identifier: str) -> dict[str, Any]:
        period_id = get_client().require_numeric_identifier(
            identifier, field_name="period_id"
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/period/{period_id}/",
            json_body=params.payload,
            business_slug=slug,
        )
        return dump_model_from_backend(PeriodSummary, result)

    return await run_batch(params.identifiers, _update)


@tool(
    name="reporting_accounting_period_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description="Delete one or more accounting periods in a single call — pass every target (period ID) in identifiers. Prefer one batched call over repeated single-target calls (each call needs its own confirmation).",
    output_schema=BatchResponse.model_json_schema(),
)
async def reporting_accounting_period_delete(
    params: IdentifiersInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(identifier: str) -> dict[str, Any]:
        period_id = get_client().require_numeric_identifier(
            identifier, field_name="period_id"
        )
        await get_client().request(
            "DELETE", f"/v1/business/{slug}/period/{period_id}/", business_slug=slug
        )
        return dump_model(DeletedResponse(id=period_id))

    return await run_batch(params.identifiers, _delete)


@tool(
    name="reporting_vat_periods_list",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
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
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
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
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Update one or more VAT periods selected by identifiers (VAT period IDs); the same payload "
        "is applied to every period. Batch all targets into one call. Each period must be editable and not reported."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def reporting_vat_period_update(
    params: IdentifiersPayloadInput,
) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _update(identifier: str) -> dict[str, Any]:
        vat_period_id = get_client().require_numeric_identifier(
            identifier, field_name="vat_period_id"
        )
        result = await get_client().request(
            "PATCH",
            f"/v1/business/{slug}/vat_period/{vat_period_id}/",
            json_body=params.payload,
            business_slug=slug,
        )
        return dump_model_from_backend(PeriodSummary, result)

    return await run_batch(params.identifiers, _update)


@tool(
    name="reporting_vat_period_delete",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    description=(
        "Delete one or more VAT periods in a single call — pass every target (VAT period ID) in identifiers. "
        "Prefer one batched call over repeated single-target calls (each call needs its own confirmation)."
    ),
    output_schema=BatchResponse.model_json_schema(),
)
async def reporting_vat_period_delete(params: IdentifiersInput) -> dict[str, Any]:
    slug = await business_slug(params.business)

    async def _delete(identifier: str) -> dict[str, Any]:
        vat_period_id = get_client().require_numeric_identifier(
            identifier, field_name="vat_period_id"
        )
        await get_client().request(
            "DELETE",
            f"/v1/business/{slug}/vat_period/{vat_period_id}/",
            business_slug=slug,
        )
        return dump_model(DeletedResponse(id=vat_period_id))

    return await run_batch(params.identifiers, _delete)


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
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Generate balance sheet report data.",
)
async def reporting_balance_sheet_retrieve(
    params: BalanceSheetReportInput,
) -> dict[str, Any]:
    return await run_report("balance-sheet", params)


@tool(
    name="reporting_equity_changes_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Generate equity changes report data.",
)
async def reporting_equity_changes_retrieve(
    params: EquityChangesReportInput,
) -> dict[str, Any]:
    return await run_report("equity-changes", params)


@tool(
    name="reporting_income_statement_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Generate income statement report data.",
)
async def reporting_income_statement_retrieve(
    params: IncomeStatementReportInput,
) -> dict[str, Any]:
    return await run_report("income-statement", params)


@tool(
    name="reporting_journal_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Generate journal report data.",
)
async def reporting_journal_retrieve(params: JournalReportInput) -> dict[str, Any]:
    return await run_report("journal", params)


@tool(
    name="reporting_ledger_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Generate ledger report data.",
)
async def reporting_ledger_retrieve(params: LedgerReportInput) -> dict[str, Any]:
    return await run_report("ledger", params)


@tool(
    name="reporting_vat_retrieve",
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    description="Generate VAT statement data.",
)
async def reporting_vat_retrieve(params: VatReportInput) -> dict[str, Any]:
    return await run_report("vat-report", params)
