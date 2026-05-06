"""Shared schema primitives and common MCP models."""

from __future__ import annotations

import base64
import json
import logging
from enum import StrEnum
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

BusinessArg = str
LOGGER = logging.getLogger(__name__)


class StrictModel(BaseModel):
    """Base model for MCP schemas."""

    model_config = ConfigDict(extra="forbid")


class AgentModel(BaseModel):
    """Base model for backend payloads serialized into agent-facing shape."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


M = TypeVar("M", bound=BaseModel)
E = TypeVar("E", bound=StrEnum)
TItem = TypeVar("TItem")


def dump_model(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True, exclude_none=True)


def dump_models(model: type[M], values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dump_model(model.model_validate(value)) for value in values]


def dump_model_from_backend(model: type[M], value: dict[str, Any]) -> dict[str, Any]:
    return dump_model(model.model_validate(value))


def tool_handle(resource: str, internal_id: int) -> str:
    payload = {"resource": resource, "id": int(internal_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def enum_or_str(enum_cls: type[E]) -> Any:
    """Accept known enum values, but pass unknown strings through."""

    by_value = {member.value: member for member in enum_cls}

    def _coerce(value: Any) -> Any:
        if isinstance(value, enum_cls):
            return value
        if isinstance(value, str):
            if value in by_value:
                return by_value[value]
            LOGGER.warning(
                "Unknown enum value '%s' for %s; passing through as raw string.",
                value,
                enum_cls.__name__,
            )
            return value
        return value

    return Annotated[enum_cls | str, BeforeValidator(_coerce)]


class PageInfo(StrictModel):
    has_next_page: bool = Field(
        default=False,
        description="True when more results are available; call the same tool again with next_cursor.",
    )
    next_cursor: str | None = Field(
        default=None,
        description="Cursor to pass to the next call of the same list tool.",
    )
    limit: int = Field(description="Maximum number of records to return in this page.")
    total_size: int | None = Field(
        default=None,
        description="Total number of matching records reported by the backend list response (`size`).",
    )


class ListEnvelope(StrictModel, Generic[TItem]):
    items: list[TItem] = Field(description="Records returned for the requested page.")
    page_info: PageInfo = Field(
        description="Pagination state for continuing the same list query."
    )
    usage_hint: str | None = Field(
        default=None,
        description="Guidance for narrowing the query or fetching the next page.",
    )


class ToolErrorPayload(StrictModel):
    error_type: str = Field(
        description="Stable error category the agent can use to choose the next step."
    )
    message: str = Field(description="Plain-language explanation of what went wrong.")
    hint: str | None = Field(
        default=None, description="Recommended next step after this error."
    )
    status_code: int | None = Field(
        default=None,
        description="NoCFO status code when the error came from a tool request.",
    )
    field_errors: dict[str, Any] | None = Field(
        default=None,
        description="Validation errors keyed by field name, useful for correcting the next call.",
    )
    current_permissions: list[str] | None = Field(
        default=None,
        description="Permissions the current user has for this business, shown when access is denied.",
    )
    candidates: list[dict[str, Any]] | None = Field(
        default=None,
        description="Possible matching records when the requested reference was ambiguous.",
    )
    feature: str | None = Field(
        default=None, description="Feature that is unavailable or caused the error."
    )
    reason: str | None = Field(
        default=None,
        description="Additional reason code or explanation that helps choose the next step.",
    )


class ResolvedBusiness(StrictModel):
    slug: str = Field(
        description="Business slug to use when you need to call tools for this exact business."
    )
    name: str | None = Field(default=None, description="Business display name.")
    source: Literal["explicit", "jwt", "single_accessible_business"] = Field(
        description="Shows whether the business was given explicitly or resolved from the current session."
    )


class DocumentSide(StrEnum):
    debit = "debit"
    credit = "credit"


class AccountAction(StrEnum):
    show = "show"
    hide = "hide"


class DocumentAction(StrEnum):
    lock = "lock"
    unlock = "unlock"
    flag = "flag"
    unflag = "unflag"


class SalesInvoiceAction(StrEnum):
    accept = "accept"
    mark_paid = "mark_paid"
    mark_unpaid = "mark_unpaid"
    mark_credit_loss = "mark_credit_loss"
    disable_recurrence = "disable_recurrence"


class SalesInvoiceStatus(StrEnum):
    draft = "DRAFT"
    accepted = "ACCEPTED"
    paid = "PAID"
    credit_loss = "CREDIT_LOSS"


class AccountType(StrEnum):
    ass = "ASS"
    ass_dep = "ASS_DEP"
    ass_vat = "ASS_VAT"
    ass_rec = "ASS_REC"
    ass_pay = "ASS_PAY"
    ass_due = "ASS_DUE"
    lia = "LIA"
    lia_equ = "LIA_EQU"
    lia_pre = "LIA_PRE"
    lia_due = "LIA_DUE"
    lia_deb = "LIA_DEB"
    lia_acc = "LIA_ACC"
    lia_vat = "LIA_VAT"
    rev = "REV"
    rev_sal = "REV_SAL"
    rev_no = "REV_NO"
    exp = "EXP"
    exp_dep = "EXP_DEP"
    exp_no = "EXP_NO"
    exp_50 = "EXP_50"
    exp_tax = "EXP_TAX"
    exp_tax_pre = "EXP_TAX_PRE"


class ContactType(StrEnum):
    unset = "UNSET"
    person = "PERSON"
    business = "BUSINESS"


class DeliveryMethod(StrEnum):
    email = "EMAIL"
    einvoice = "EINVOICE"
    elasku = "ELASKU"
    paper = "PAPER"


class RelationType(StrEnum):
    accrual_pair = "ACCRUAL_PAIR"


class RelationRole(StrEnum):
    accrual = "ACCRUAL"
    settlement = "SETTLEMENT"


class ConstantsKind(StrEnum):
    vat_codes = "vat_codes"
    vat_rates = "vat_rates"


class DocsKind(StrEnum):
    blueprint = "blueprint"
    glossary = "glossary"


class DateRangeInput(StrictModel):
    date_from: str = Field(
        description="Start date for a date range, inclusive. Format: YYYY-MM-DD."
    )
    date_to: str = Field(
        description="End date for a date range, inclusive. Format: YYYY-MM-DD."
    )


class PointInTimeInput(StrictModel):
    date_at: str = Field(description="Point-in-time report date. Format: YYYY-MM-DD.")


class PointInTimeReportColumnInput(StrictModel):
    name: str | None = Field(
        default=None,
        description="Optional label shown for this report column in the output.",
    )
    date_at: str = Field(
        description="Point-in-time date for balance-sheet style reports. Format: YYYY-MM-DD.",
    )


class DateRangeReportColumnInput(StrictModel):
    name: str | None = Field(
        default=None,
        description="Optional label shown for this report column in the output.",
    )
    date_from: str = Field(
        description="Start date for range-based reports. Format: YYYY-MM-DD.",
    )
    date_to: str = Field(
        description="End date for range-based reports. Format: YYYY-MM-DD.",
    )


class TypedReportInputBase(StrictModel):
    business: BusinessArg = Field(
        default="current",
        description="Use current by default; provide a business slug only when the user explicitly selects another business.",
    )
    tag_names: list[str] | None = Field(
        default=None,
        description="Shared business tag names used to filter report calculations.",
    )
    extend_accounts: bool = Field(
        default=False,
        description="When true, include account-level drill-down rows for supported reports.",
    )
    append_comparison_columns: bool = Field(
        default=False,
        description="When true and column count is small enough, add comparison columns.",
    )


class PointInTimeTypedReportInput(TypedReportInputBase):
    columns: list[PointInTimeReportColumnInput] = Field(
        description="Columns for point-in-time reports. Use date_at for each column.",
    )


class DateRangeTypedReportInput(TypedReportInputBase):
    columns: list[DateRangeReportColumnInput] = Field(
        description="Columns for period reports. Use date_from and date_to for each column.",
    )


class BalanceSheetReportInput(PointInTimeTypedReportInput):
    pass


class IncomeStatementReportInput(DateRangeTypedReportInput):
    pass


class EquityChangesReportInput(DateRangeTypedReportInput):
    pass


class JournalReportInput(DateRangeTypedReportInput):
    pass


class LedgerReportInput(DateRangeTypedReportInput):
    pass


class VatReportInput(DateRangeTypedReportInput):
    pass


class BusinessContextInput(StrictModel):
    business: BusinessArg = Field(
        default="current",
        description="Use current by default; provide a business slug only when the user explicitly selects another business.",
    )


class PaginationInput(StrictModel):
    limit: int = Field(
        default=10, description="Maximum number of records to return in this page."
    )
    cursor: str | None = Field(
        default=None,
        description="Cursor from the previous page_info.next_cursor for the same list tool.",
    )


class BusinessPaginationInput(PaginationInput):
    business: BusinessArg = Field(
        default="current",
        description="Use current by default; provide a business slug only when the user explicitly selects another business.",
    )
    query: str | None = Field(
        default=None,
        description="Free-text search term for narrowing results when exact filters are not enough.",
    )


class PayloadInput(BusinessContextInput):
    payload: dict[str, Any] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class ToolHandleInput(BusinessContextInput):
    tool_handle: str = Field(
        description="Value copied from items[].tool_handle in a list response. Pass it unchanged to the matching retrieve tool."
    )


class InternalIdInput(BusinessContextInput):
    internal_id: int = Field(
        description="Internal numeric ID for this resource when a direct ID is known."
    )


class ExactResourceInput(BusinessContextInput):
    tool_handle: str | None = Field(
        default=None,
        description="Value copied from items[].tool_handle in a list response. Pass it unchanged to the matching retrieve tool.",
    )
    internal_id: int | None = Field(
        default=None, description="Internal numeric ID for this resource."
    )

    @model_validator(mode="after")
    def validate_exact_resource_selector(self) -> "ExactResourceInput":
        if (self.tool_handle is None and self.internal_id is None) or (
            self.tool_handle is not None and self.internal_id is not None
        ):
            raise ValueError("Provide exactly one of tool_handle or internal_id")
        return self


class IdentifierInput(BusinessContextInput):
    identifier: str = Field(
        description="Identifier for this resource. Prefer the exact value named in the tool description."
    )


class IdentifierPayloadInput(IdentifierInput):
    payload: dict[str, Any] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class IdInput(BusinessContextInput):
    id: int = Field(
        description="ID shown by the matching list or retrieve tool for this resource."
    )


class IdPayloadInput(IdInput):
    payload: dict[str, Any] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class DeletedResponse(StrictModel):
    deleted: bool = Field(
        default=True, description="True when the delete operation succeeded."
    )
    id: int | None = Field(
        default=None,
        description="Deleted resource ID for ID-based resources. Expand it with the corresponding *_retrieve tool.",
    )
    account_number: int | None = Field(
        default=None, description="User-facing bookkeeping account number, e.g. 1910."
    )
    document_number: str | None = Field(
        default=None, description="Bookkeeping document number visible to the user."
    )
    invoice_number: int | str | None = Field(
        default=None, description="Invoice number visible to the user."
    )
    tag_id: int | None = Field(
        default=None,
        description="Deleted tag ID. Use bookkeeping_tag_retrieve to expand this ID.",
    )
    file_id: int | None = Field(
        default=None,
        description="Deleted file ID. Use bookkeeping_file_retrieve to expand this ID.",
    )
    relation_id: int | None = Field(
        default=None,
        description="Deleted relation ID. Use bookkeeping_document_relations_list to see current relation state.",
    )


class ActionResponse(StrictModel):
    ok: bool = Field(
        default=True, description="True when the requested action succeeded."
    )
    action: str = Field(description="Action to run on the selected resource.")
    account_number: int | None = Field(
        default=None, description="User-facing bookkeeping account number, e.g. 1910."
    )


class ItemsResponse(StrictModel):
    items: list[Any] = Field(description="Records returned for the requested page.")


class TextResourceResponse(StrictModel):
    content: str = Field(
        description="Guidance text for the agent to read before using related tools."
    )


class BusinessSummary(AgentModel):
    slug: str | None = Field(
        default=None,
        description="Business slug to use when you need to call tools for this exact business.",
    )
    name: str | None = Field(default=None, description="Display name.")
    form_name: str | None = Field(
        default=None, description="Business legal form display name."
    )
    identifiers: Any | None = Field(
        default=None,
        description="Business identifiers such as VAT or registration numbers.",
    )


class UserSummary(AgentModel):
    id: int | None = Field(
        default=None,
        description="ID shown by the matching list or retrieve tool for this resource.",
    )
    email: str | None = Field(
        default=None, description="User or contact email address."
    )
    first_name: str | None = Field(default=None, description="User first name.")
    last_name: str | None = Field(default=None, description="User last name.")
    language: str | None = Field(default=None, description="Preferred language code.")
