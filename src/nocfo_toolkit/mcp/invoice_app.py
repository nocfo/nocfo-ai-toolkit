"""Additive MCP Apps capability for interactive invoice creation."""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastmcp import Context
from fastmcp.apps.config import UI_EXTENSION_ID
from fastmcp.exceptions import ToolError
from fastmcp.utilities.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

try:
    from prefab_ui.actions import SetState
    from prefab_ui.actions.mcp import CallTool
    from prefab_ui.app import PrefabApp
    from prefab_ui.components import (
        Accordion,
        AccordionItem,
        Alert,
        AlertDescription,
        AlertTitle,
        Badge,
        Button,
        Card,
        CardContent,
        CardFooter,
        CardHeader,
        Column,
        Form,
        H3,
        If,
        Input,
        Muted,
        Select,
        SelectOption,
        Textarea,
    )
    from prefab_ui.rx import ERROR, RESULT, STATE

    _HAS_PREFAB_UI = True
except ImportError:  # pragma: no cover - exercised via fallback tests
    _HAS_PREFAB_UI = False
    PrefabApp = Any  # type: ignore[assignment,misc]


logger = get_logger(__name__)

_INVOICE_CREATE_PATH_RE = re.compile(r"^/v1/invoicing/\{[^}]+\}/invoice/$")
_CONTACTS_LIST_PATH_RE = re.compile(r"^/v1/business/\{[^}]+\}/contacts/$")
_PRODUCTS_LIST_PATH_RE = re.compile(r"^/v1/invoicing/\{[^}]+\}/product/$")
_DEFAULT_UNIT_OPTIONS: tuple[str, ...] = ("kpl", "h", "pv", "kk")


@dataclass(frozen=True)
class InvoiceAppOptions:
    """Configuration for the additive invoice app capability."""

    form_tool_name: str = "invoice_create_form"
    submit_tool_name: str = "invoice_create_submit"


def register_invoice_app_capability(
    server: FastMCP,
    *,
    options: InvoiceAppOptions | None = None,
) -> None:
    """Register invoice app tools without modifying existing OpenAPI tools."""
    opts = options or InvoiceAppOptions()
    invoice_create_tool_name = _locate_tool_name_by_route(
        server,
        method="POST",
        path_pattern=_INVOICE_CREATE_PATH_RE,
    )
    if not invoice_create_tool_name:
        logger.warning(
            "Invoice app capability skipped: invoice create OpenAPI tool not found."
        )
        return
    contacts_list_tool_name = _locate_tool_name_by_route(
        server,
        method="GET",
        path_pattern=_CONTACTS_LIST_PATH_RE,
    )
    products_list_tool_name = _locate_tool_name_by_route(
        server,
        method="GET",
        path_pattern=_PRODUCTS_LIST_PATH_RE,
    )

    @server.tool(
        name=opts.submit_tool_name,
        description=(
            "Submit invoice payload to NoCFO. Returns validation errors in a stable "
            "structured format so callers can correct input and retry."
        ),
    )
    async def invoice_create_submit(
        business_slug: str,
        receiver: str | int | None = None,
        invoicing_date: str | None = None,
        payment_condition_days: str | int | None = 14,
        reference: str | None = None,
        description: str | None = None,
        contact_person: str | None = None,
        seller_reference: str | None = None,
        buyer_reference: str | None = None,
        row_name: str | None = None,
        row_unit: str | None = "kpl",
        row_amount: str | float | int | None = None,
        row_product_count: str | float | int | None = 1,
        row_vat_rate: str | float | int | None = None,
        row_vat_code: str | int | None = None,
        row_description: str | None = None,
        product_id: str | int | None = None,
        attachment_ids: str | list[int] | list[str] | None = None,
        extra_payload_json: str | None = None,
        invoice_payload: dict[str, Any] | None = None,
        preset_payload: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            return {
                "status": "error",
                "error": {"summary": "MCP context is not available for this call."},
            }

        payload_result = _build_invoice_payload(
            receiver=receiver,
            invoicing_date=invoicing_date,
            payment_condition_days=payment_condition_days,
            reference=reference,
            description=description,
            contact_person=contact_person,
            seller_reference=seller_reference,
            buyer_reference=buyer_reference,
            row_name=row_name,
            row_unit=row_unit,
            row_amount=row_amount,
            row_product_count=row_product_count,
            row_vat_rate=row_vat_rate,
            row_vat_code=row_vat_code,
            row_description=row_description,
            product_id=product_id,
            attachment_ids=attachment_ids,
            extra_payload_json=extra_payload_json,
            invoice_payload=invoice_payload,
            preset_payload=preset_payload,
        )
        if payload_result["errors"]:
            return {
                "status": "validation_error",
                "error": {
                    "summary": "Input validation failed before backend request.",
                    "field_errors": {"input": payload_result["errors"]},
                },
                "error_text": "; ".join(payload_result["errors"]),
                "warnings": payload_result["warnings"],
                "submitted_payload": payload_result["payload"],
            }

        call_arguments = {
            "business_slug": business_slug,
            **payload_result["payload"],
        }
        try:
            tool_result = await ctx.fastmcp.call_tool(
                invoice_create_tool_name,
                call_arguments,
            )
        except ToolError as exc:
            parsed_error = _parse_tool_error(str(exc))
            return {
                "status": "validation_error",
                "error": parsed_error,
                "error_text": _format_error_text(parsed_error),
                "warnings": payload_result["warnings"],
                "submitted_payload": payload_result["payload"],
            }

        created_invoice = _unwrap_tool_result_payload(tool_result.structured_content)
        return {
            "status": "created",
            "invoice": created_invoice,
            "warnings": payload_result["warnings"],
        }

    @server.tool(
        name=opts.form_tool_name,
        description=(
            "Open an interactive invoice creation app. Supports preset values and "
            "returns backend validation feedback for correction."
        ),
        app=True if _HAS_PREFAB_UI else None,
    )
    async def invoice_create_form(
        business_slug: str,
        preset: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> Any:
        receiver_options: list[dict[str, Any]] = []
        product_options: list[dict[str, Any]] = []
        if ctx is not None:
            receiver_options = await _fetch_receiver_options(
                ctx=ctx,
                tool_name=contacts_list_tool_name,
                business_slug=business_slug,
            )
            product_options = await _fetch_product_options(
                ctx=ctx,
                tool_name=products_list_tool_name,
                business_slug=business_slug,
            )
        defaults = _build_form_defaults(
            business_slug=business_slug,
            preset=preset,
            receiver_options=receiver_options,
            product_options=product_options,
        )

        if (
            ctx is None
            or not _HAS_PREFAB_UI
            or not ctx.client_supports_extension(UI_EXTENSION_ID)
        ):
            return _build_non_ui_form_payload(
                defaults=defaults,
                submit_tool_name=opts.submit_tool_name,
            )
        return _build_prefab_form(
            defaults=defaults,
            submit_tool_name=opts.submit_tool_name,
        )


def _locate_tool_name_by_route(
    server: FastMCP,
    *,
    method: str,
    path_pattern: re.Pattern[str],
) -> str | None:
    target_method = method.upper()
    for provider in getattr(server, "providers", []):
        tools = getattr(provider, "_tools", None)
        if not isinstance(tools, dict):
            continue
        for tool in tools.values():
            route = getattr(tool, "_route", None)
            route_method = str(getattr(route, "method", "")).upper()
            route_path = str(getattr(route, "path", ""))
            if route_method != target_method:
                continue
            if path_pattern.fullmatch(route_path):
                return str(getattr(tool, "name", ""))
    return None


async def _fetch_receiver_options(
    *,
    ctx: Context,
    tool_name: str | None,
    business_slug: str,
) -> list[dict[str, Any]]:
    if not tool_name:
        return []
    try:
        result = await ctx.fastmcp.call_tool(
            tool_name,
            {"business_slug": business_slug},
        )
    except ToolError:
        return []

    payload = _unwrap_tool_result_payload(result.structured_content)
    return _normalize_receiver_options(payload)


async def _fetch_product_options(
    *,
    ctx: Context,
    tool_name: str | None,
    business_slug: str,
) -> list[dict[str, Any]]:
    if not tool_name:
        return []
    try:
        result = await ctx.fastmcp.call_tool(
            tool_name,
            {"business_slug": business_slug},
        )
    except ToolError:
        return []

    payload = _unwrap_tool_result_payload(result.structured_content)
    return _normalize_product_options(payload)


def _normalize_receiver_options(payload: dict[str, Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for item in _extract_results_from_list_payload(payload):
        receiver_id = _coerce_int(item.get("id"))
        if receiver_id is None:
            continue
        name = _clean_optional(item.get("name")) or f"Receiver {receiver_id}"
        receiver_type = _clean_optional(item.get("type")) or "CONTACT"
        options.append(
            {
                "id": receiver_id,
                "label": f"{name} ({receiver_type})",
                "name": name,
                "type": receiver_type,
            }
        )
    return options


def _normalize_product_options(payload: dict[str, Any]) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for item in _extract_results_from_list_payload(payload):
        product_id = _coerce_int(item.get("id"))
        if product_id is None:
            continue
        name = _clean_optional(item.get("name")) or f"Product {product_id}"
        unit = _clean_optional(item.get("unit")) or "kpl"
        vat_rate = _coerce_float(item.get("vat_rate"))
        vat_code = _coerce_int(item.get("vat_code"))
        label_parts = [name, f"unit={unit}"]
        if vat_rate is not None:
            label_parts.append(f"VAT {vat_rate}")
        if vat_code is not None:
            label_parts.append(f"code={vat_code}")
        options.append(
            {
                "id": product_id,
                "label": " | ".join(label_parts),
                "name": name,
                "unit": unit,
                "vat_rate": vat_rate,
                "vat_code": vat_code,
            }
        )
    return options


def _extract_results_from_list_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        results: Any = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def _build_form_defaults(
    *,
    business_slug: str,
    preset: dict[str, Any] | None,
    receiver_options: list[dict[str, Any]] | None = None,
    product_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data = copy.deepcopy(preset) if isinstance(preset, dict) else {}
    receiver_options = list(receiver_options or [])
    product_options = list(product_options or [])

    first_row: dict[str, Any] = {}
    rows = data.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        first_row = rows[0]

    product_id = _to_string_or_none(first_row.get("product")) or _to_string_or_none(
        data.get("product_id")
    )
    attachment_ids = data.get("attachments")
    attachment_ids_text = ""
    if isinstance(attachment_ids, list):
        attachment_ids_text = ",".join(
            str(item) for item in attachment_ids if _coerce_int(item) is not None
        )

    default_unit_options = list(_DEFAULT_UNIT_OPTIONS)
    for option in product_options:
        unit = _clean_optional(option.get("unit"))
        if unit and unit not in default_unit_options:
            default_unit_options.append(unit)

    defaults: dict[str, Any] = {
        "business_slug": business_slug,
        "receiver": _to_string_or_none(data.get("receiver")),
        "invoicing_date": _to_string_or_none(data.get("invoicing_date"))
        or dt.date.today().isoformat(),
        "payment_condition_days": _to_string_or_none(data.get("payment_condition_days"))
        or "14",
        "reference": _to_string_or_none(data.get("reference")) or "",
        "description": _to_string_or_none(data.get("description")) or "",
        "contact_person": _to_string_or_none(data.get("contact_person")) or "",
        "seller_reference": _to_string_or_none(data.get("seller_reference")) or "",
        "buyer_reference": _to_string_or_none(data.get("buyer_reference")) or "",
        "product_id": product_id or "",
        "row_name": _to_string_or_none(first_row.get("name")) or "",
        "row_unit": _to_string_or_none(first_row.get("unit")) or "kpl",
        "row_amount": _to_string_or_none(first_row.get("amount")) or "",
        "row_product_count": _to_string_or_none(first_row.get("product_count")) or "1",
        "row_vat_rate": _to_string_or_none(first_row.get("vat_rate")) or "",
        "row_vat_code": _to_string_or_none(first_row.get("vat_code")) or "1",
        "row_description": _to_string_or_none(first_row.get("description")) or "",
        "attachment_ids": attachment_ids_text,
        "extra_payload_json": "",
        "preset_payload": data,
        "receiver_options": receiver_options,
        "product_options": product_options,
        "unit_options": default_unit_options,
        "attachment_hints": (
            "Optional: provide existing attachment IDs (comma separated). "
            "Use NoCFO files API beforehand to upload and collect IDs."
        ),
    }

    warnings: list[str] = []
    if not defaults["receiver"]:
        warnings.append("Preset is missing receiver; user input is required.")
    if not defaults["row_name"]:
        warnings.append("Preset is missing row_name; user input is required.")
    if not defaults["row_amount"]:
        warnings.append("Preset is missing row_amount; user input is required.")
    defaults["preset_warnings"] = warnings
    return defaults


def _build_non_ui_form_payload(
    *,
    defaults: dict[str, Any],
    submit_tool_name: str,
) -> dict[str, Any]:
    return {
        "mode": "fallback_form",
        "ui_supported": False,
        "title": "Create sales invoice",
        "submit_tool": submit_tool_name,
        "prefill": {
            key: value
            for key, value in defaults.items()
            if key
            not in {
                "preset_payload",
                "preset_warnings",
                "receiver_options",
                "product_options",
                "unit_options",
                "attachment_hints",
            }
        },
        "receiver_options": defaults.get("receiver_options", []),
        "product_options": defaults.get("product_options", []),
        "unit_options": defaults.get("unit_options", list(_DEFAULT_UNIT_OPTIONS)),
        "attachment_hints": defaults.get("attachment_hints"),
        "fields": [
            {"name": "receiver", "type": "integer", "required": True},
            {"name": "invoicing_date", "type": "date", "required": False},
            {"name": "payment_condition_days", "type": "integer", "required": False},
            {"name": "reference", "type": "string", "required": False},
            {"name": "description", "type": "string", "required": False},
            {"name": "product_id", "type": "integer", "required": False},
            {"name": "row_name", "type": "string", "required": True},
            {"name": "row_amount", "type": "number", "required": True},
            {"name": "row_product_count", "type": "number", "required": False},
            {"name": "row_unit", "type": "string", "required": False},
            {"name": "row_vat_rate", "type": "number", "required": False},
            {"name": "row_vat_code", "type": "integer", "required": False},
            {"name": "attachment_ids", "type": "string", "required": False},
            {
                "name": "extra_payload_json",
                "type": "json_string",
                "required": False,
                "description": "Optional JSON object merged into payload.",
            },
        ],
        "warnings": defaults.get("preset_warnings", []),
    }


def _build_prefab_form(
    *,
    defaults: dict[str, Any],
    submit_tool_name: str,
) -> PrefabApp:
    receiver_options = defaults.get("receiver_options", [])
    product_options = defaults.get("product_options", [])
    unit_options = defaults.get("unit_options", list(_DEFAULT_UNIT_OPTIONS))

    with Card(css_class="max-w-4xl mx-auto") as view:
        with CardHeader(), Column(gap=2):
            H3("Create sales invoice")
            with Column(gap=1):
                Badge(
                    f"Receivers: {len(receiver_options)}",
                    variant="secondary",
                )
                Badge(
                    f"Products: {len(product_options)}",
                    variant="secondary",
                )

        with CardContent(), Column(gap=4):
            Muted(
                "Agent may prefill known values (for example receiver), then user can "
                "complete missing fields and submit."
            )

            if defaults.get("preset_warnings"):
                with Alert(variant="warning"):
                    AlertTitle("Preset needs attention")
                    AlertDescription("; ".join(defaults["preset_warnings"]))

            with If(STATE.server_error):
                with Alert(variant="destructive"):
                    AlertTitle("Unexpected error")
                    AlertDescription(STATE.server_error)

            with If(STATE.submission.status == "validation_error"):
                with Alert(variant="destructive"):
                    AlertTitle("Validation error")
                    AlertDescription(STATE.submission.error_text)

            with If(STATE.submission.status == "created"):
                with Alert(variant="success"):
                    AlertTitle("Invoice created")
                    AlertDescription(
                        "Invoice ID: "
                        + str(STATE.submission.invoice.id.default("unknown"))
                    )

            with Form(
                on_submit=CallTool(
                    submit_tool_name,
                    arguments={
                        "business_slug": STATE.business_slug,
                        "receiver": STATE.receiver,
                        "invoicing_date": STATE.invoicing_date,
                        "payment_condition_days": STATE.payment_condition_days,
                        "reference": STATE.reference,
                        "description": STATE.description,
                        "contact_person": STATE.contact_person,
                        "seller_reference": STATE.seller_reference,
                        "buyer_reference": STATE.buyer_reference,
                        "product_id": STATE.product_id,
                        "row_name": STATE.row_name,
                        "row_unit": STATE.row_unit,
                        "row_amount": STATE.row_amount,
                        "row_product_count": STATE.row_product_count,
                        "row_vat_rate": STATE.row_vat_rate,
                        "row_vat_code": STATE.row_vat_code,
                        "row_description": STATE.row_description,
                        "attachment_ids": STATE.attachment_ids,
                        "extra_payload_json": STATE.extra_payload_json,
                        "preset_payload": STATE.preset_payload,
                    },
                    on_success=[
                        SetState("server_error", ""),
                        SetState("submission", RESULT),
                    ],
                    on_error=[SetState("server_error", ERROR)],
                )
            ):
                if receiver_options:
                    with Select(
                        name="receiver",
                        value=str(defaults.get("receiver") or ""),
                        placeholder="Select receiver",
                        required=True,
                    ):
                        for option in receiver_options:
                            opt_id = str(option.get("id"))
                            SelectOption(
                                value=opt_id,
                                label=str(option.get("label") or opt_id),
                                selected=opt_id == str(defaults.get("receiver") or ""),
                            )
                else:
                    Input(
                        name="receiver",
                        input_type="number",
                        value=str(defaults.get("receiver") or ""),
                        placeholder="Receiver contact id",
                        required=True,
                        min=1,
                    )

                Input(
                    name="invoicing_date",
                    input_type="date",
                    value=str(defaults.get("invoicing_date") or ""),
                )
                Input(
                    name="payment_condition_days",
                    input_type="number",
                    value=str(defaults.get("payment_condition_days") or "14"),
                    min=0,
                )
                Textarea(
                    name="description",
                    value=str(defaults.get("description") or ""),
                    placeholder="Invoice description",
                    rows=2,
                )

                if product_options:
                    with Select(
                        name="product_id",
                        value=str(defaults.get("product_id") or ""),
                        placeholder="Select product (optional)",
                    ):
                        for option in product_options:
                            opt_id = str(option.get("id"))
                            SelectOption(
                                value=opt_id,
                                label=str(option.get("label") or opt_id),
                                selected=opt_id == str(defaults.get("product_id") or ""),
                            )
                else:
                    Input(
                        name="product_id",
                        input_type="number",
                        value=str(defaults.get("product_id") or ""),
                        placeholder="Product id (optional)",
                        min=1,
                    )

                Input(
                    name="row_name",
                    value=str(defaults.get("row_name") or ""),
                    placeholder="Row name",
                    required=True,
                )
                Input(
                    name="row_amount",
                    input_type="number",
                    value=str(defaults.get("row_amount") or ""),
                    placeholder="Row amount",
                    required=True,
                    min=0.01,
                )
                Input(
                    name="row_product_count",
                    input_type="number",
                    value=str(defaults.get("row_product_count") or "1"),
                    min=0.0001,
                )

                with Select(
                    name="row_unit",
                    value=str(defaults.get("row_unit") or "kpl"),
                    placeholder="Select unit",
                ):
                    for unit in unit_options:
                        SelectOption(
                            value=unit,
                            label=unit,
                            selected=unit == str(defaults.get("row_unit") or "kpl"),
                        )

                with Accordion(multiple=True, default_open_items=[0]):
                    with AccordionItem(title="Advanced invoice options", value="advanced"):
                        Input(
                            name="reference",
                            value=str(defaults.get("reference") or ""),
                            placeholder="Reference number (optional)",
                        )
                        Input(
                            name="contact_person",
                            value=str(defaults.get("contact_person") or ""),
                            placeholder="Contact person (optional)",
                        )
                        Input(
                            name="seller_reference",
                            value=str(defaults.get("seller_reference") or ""),
                            placeholder="Seller reference (optional)",
                        )
                        Input(
                            name="buyer_reference",
                            value=str(defaults.get("buyer_reference") or ""),
                            placeholder="Buyer reference (optional)",
                        )
                        Input(
                            name="row_vat_rate",
                            input_type="number",
                            value=str(defaults.get("row_vat_rate") or ""),
                            placeholder="VAT rate (optional)",
                            min=0,
                        )
                        Input(
                            name="row_vat_code",
                            input_type="number",
                            value=str(defaults.get("row_vat_code") or "1"),
                            placeholder="VAT code",
                            min=1,
                        )
                        Textarea(
                            name="row_description",
                            value=str(defaults.get("row_description") or ""),
                            placeholder="Row description (optional)",
                            rows=2,
                        )
                        Textarea(
                            name="attachment_ids",
                            value=str(defaults.get("attachment_ids") or ""),
                            placeholder="Attachment IDs (comma-separated), e.g. 12,34",
                            rows=2,
                        )
                        Muted(str(defaults.get("attachment_hints") or ""))
                        Textarea(
                            name="extra_payload_json",
                            value=str(defaults.get("extra_payload_json") or ""),
                            placeholder='Optional JSON merged into payload, e.g. {"delivery_method":"EMAIL"}',
                            rows=3,
                        )

                Button("Create invoice")

        with CardFooter():
            Muted(
                "Submission is sent to backend invoice create endpoint. "
                "Validation issues are shown above for correction and re-submit."
            )

    return PrefabApp(
        view=view,
        state={
            "business_slug": defaults["business_slug"],
            "receiver": defaults["receiver"],
            "invoicing_date": defaults["invoicing_date"],
            "payment_condition_days": defaults["payment_condition_days"],
            "reference": defaults["reference"],
            "description": defaults["description"],
            "contact_person": defaults["contact_person"],
            "seller_reference": defaults["seller_reference"],
            "buyer_reference": defaults["buyer_reference"],
            "product_id": defaults["product_id"],
            "row_name": defaults["row_name"],
            "row_unit": defaults["row_unit"],
            "row_amount": defaults["row_amount"],
            "row_product_count": defaults["row_product_count"],
            "row_vat_rate": defaults["row_vat_rate"],
            "row_vat_code": defaults["row_vat_code"],
            "row_description": defaults["row_description"],
            "attachment_ids": defaults["attachment_ids"],
            "extra_payload_json": defaults["extra_payload_json"],
            "preset_payload": defaults["preset_payload"],
            "receiver_options": defaults.get("receiver_options", []),
            "product_options": defaults.get("product_options", []),
            "server_error": "",
            "submission": {
                "status": "idle",
                "error_text": "",
                "invoice": {},
            },
        },
    )


def _build_invoice_payload(
    *,
    receiver: str | int | None,
    invoicing_date: str | None,
    payment_condition_days: str | int | None,
    reference: str | None,
    description: str | None,
    contact_person: str | None,
    seller_reference: str | None,
    buyer_reference: str | None,
    row_name: str | None,
    row_unit: str | None,
    row_amount: str | float | int | None,
    row_product_count: str | float | int | None,
    row_vat_rate: str | float | int | None,
    row_vat_code: str | int | None,
    row_description: str | None,
    product_id: str | int | None,
    attachment_ids: str | list[int] | list[str] | None,
    extra_payload_json: str | None,
    invoice_payload: dict[str, Any] | None,
    preset_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = (
        copy.deepcopy(invoice_payload)
        if isinstance(invoice_payload, dict)
        else copy.deepcopy(preset_payload) if isinstance(preset_payload, dict) else {}
    )
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        payload = {}

    if invoice_payload is None:
        receiver_int = _coerce_int(receiver)
        if receiver_int is None:
            errors.append("receiver must be a valid integer.")
        else:
            payload["receiver"] = receiver_int

        condition_days = _coerce_int(payment_condition_days)
        if condition_days is not None:
            payload["payment_condition_days"] = condition_days
        elif payment_condition_days not in (None, ""):
            errors.append("payment_condition_days must be an integer.")

        cleaned_date = _clean_optional(invoicing_date)
        if cleaned_date:
            payload["invoicing_date"] = cleaned_date
        elif "invoicing_date" not in payload:
            payload["invoicing_date"] = dt.date.today().isoformat()

        for key, value in (
            ("reference", reference),
            ("description", description),
            ("contact_person", contact_person),
            ("seller_reference", seller_reference),
            ("buyer_reference", buyer_reference),
        ):
            cleaned = _clean_optional(value)
            if cleaned is not None:
                payload[key] = cleaned

        row = _build_row_payload(
            row_name=row_name,
            row_unit=row_unit,
            row_amount=row_amount,
            row_product_count=row_product_count,
            row_vat_rate=row_vat_rate,
            row_vat_code=row_vat_code,
            row_description=row_description,
            product_id=product_id,
        )
        if row["errors"]:
            errors.extend(row["errors"])
        elif row["value"] is not None:
            payload["rows"] = [row["value"]]
        elif not payload.get("rows"):
            errors.append(
                "Either provide row fields or include rows in invoice_payload/preset_payload."
            )

        normalized_attachments = _normalize_attachment_ids(attachment_ids)
        if normalized_attachments["errors"]:
            errors.extend(normalized_attachments["errors"])
        elif normalized_attachments["value"] is not None:
            payload["attachments"] = normalized_attachments["value"]

    extra_payload = _parse_optional_json_object(extra_payload_json)
    if isinstance(extra_payload, dict):
        payload = _deep_merge(payload, extra_payload)
    elif extra_payload_json and extra_payload is None:
        errors.append("extra_payload_json must be a valid JSON object.")

    if "rows" not in payload:
        warnings.append("No rows detected in payload; backend may reject the request.")

    return {"payload": payload, "errors": errors, "warnings": warnings}


def _build_row_payload(
    *,
    row_name: str | None,
    row_unit: str | None,
    row_amount: str | float | int | None,
    row_product_count: str | float | int | None,
    row_vat_rate: str | float | int | None,
    row_vat_code: str | int | None,
    row_description: str | None,
    product_id: str | int | None,
) -> dict[str, Any]:
    errors: list[str] = []
    cleaned_name = _clean_optional(row_name)
    cleaned_amount = _coerce_float(row_amount)
    cleaned_count = _coerce_float(row_product_count)
    cleaned_vat = _coerce_float(row_vat_rate)
    cleaned_vat_code = _coerce_int(row_vat_code)
    cleaned_product_id = _coerce_int(product_id)

    if cleaned_name is None and row_amount in (None, "", 0, 0.0):
        return {"value": None, "errors": []}

    if cleaned_name is None:
        errors.append("row_name is required when row_amount is provided.")
    if cleaned_amount is None:
        errors.append("row_amount must be a valid number.")
    if errors:
        return {"value": None, "errors": errors}

    row: dict[str, Any] = {
        "name": cleaned_name,
        "amount": cleaned_amount,
        "unit": _clean_optional(row_unit) or "kpl",
        "product_count": cleaned_count if cleaned_count is not None else 1.0,
        "vat_code": cleaned_vat_code if cleaned_vat_code is not None else 1,
    }
    if cleaned_vat is not None:
        row["vat_rate"] = cleaned_vat
    if cleaned_product_id is not None:
        row["product"] = cleaned_product_id
    cleaned_row_description = _clean_optional(row_description)
    if cleaned_row_description:
        row["description"] = cleaned_row_description
    return {"value": row, "errors": []}


def _normalize_attachment_ids(
    value: str | list[int] | list[str] | None,
) -> dict[str, Any]:
    if value is None:
        return {"value": None, "errors": []}

    if isinstance(value, list):
        normalized: list[int] = []
        for item in value:
            attachment_id = _coerce_int(item)
            if attachment_id is None:
                return {"value": None, "errors": ["attachment_ids must contain integers."]}
            normalized.append(attachment_id)
        return {"value": normalized or None, "errors": []}

    text = str(value).strip()
    if not text:
        return {"value": None, "errors": []}
    tokens = [token.strip() for token in re.split(r"[,\s]+", text) if token.strip()]
    normalized_ids: list[int] = []
    for token in tokens:
        attachment_id = _coerce_int(token)
        if attachment_id is None:
            return {
                "value": None,
                "errors": ["attachment_ids must be comma or space separated integers."],
            }
        normalized_ids.append(attachment_id)
    return {"value": normalized_ids or None, "errors": []}


def _parse_tool_error(raw_error: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_error)
    except json.JSONDecodeError:
        return {"summary": raw_error}

    if not isinstance(payload, dict):
        return {"summary": raw_error}

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = raw_error

    parsed: dict[str, Any] = {"summary": summary}
    for key in ("error_type", "status_code", "backend_error_code", "hint"):
        if key in payload:
            parsed[key] = payload[key]
    if isinstance(payload.get("field_errors"), dict):
        parsed["field_errors"] = payload["field_errors"]
    return parsed


def _format_error_text(parsed_error: dict[str, Any]) -> str:
    summary = str(parsed_error.get("summary") or "Request failed.")
    field_errors = parsed_error.get("field_errors")
    if not isinstance(field_errors, dict) or not field_errors:
        return summary

    parts: list[str] = []
    for key, value in field_errors.items():
        if isinstance(value, list):
            detail = ", ".join(str(item) for item in value)
        else:
            detail = str(value)
        parts.append(f"{key}: {detail}")
    return summary + " | " + "; ".join(parts)


def _unwrap_tool_result_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if set(payload.keys()) == {"result"} and isinstance(payload["result"], dict):
        return payload["result"]
    return payload


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in incoming.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
            and merged.get(key) is not None
        ):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def _parse_optional_json_object(value: str | None) -> dict[str, Any] | None:
    cleaned = _clean_optional(value)
    if not cleaned:
        return None
    try:
        decoded = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _to_string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    cleaned = str(value).strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None
