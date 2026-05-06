"""Bookkeeping account schemas."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    AccountType,
    AccountAction,
    AgentModel,
    BusinessContextInput,
    BusinessPaginationInput,
    enum_or_str,
    tool_handle,
)


class AccountListInput(BusinessPaginationInput):
    number: int | None = Field(
        default=None, description="User-facing bookkeeping account number."
    )
    number_from: int | None = Field(
        default=None,
        description="Include accounts whose number is at least this value.",
    )
    number_to: int | None = Field(
        default=None, description="Include accounts whose number is at most this value."
    )
    type: enum_or_str(AccountType) | None = Field(
        default=None,
        description="Account type/category filter. Preferred values are AccountType codes like ASS_PAY, LIA_DUE, REV_SAL, or EXP.",
    )
    is_used: bool | None = Field(
        default=None, description="True for accounts that have entries posted to them."
    )
    is_shown: bool | None = Field(
        default=None,
        description="True for accounts visible in normal account selection lists.",
    )

    def query_params(self) -> dict[str, Any]:
        params = {
            "number": self.number,
            "number_gte": self.number_from,
            "number_lte": self.number_to,
            "search": self.query,
            "type": (
                self.type.value if isinstance(self.type, AccountType) else self.type
            ),
            "is_used": self.is_used,
            "is_shown": self.is_shown,
        }
        return {key: value for key, value in params.items() if value is not None}


class AccountNumberInput(BusinessContextInput):
    account_number: int = Field(
        description="User-facing bookkeeping account number, e.g. 1910."
    )


class AccountPayloadInput(AccountNumberInput):
    payload: dict[str, Any] = Field(
        description="Fields to create or update. Prefer user-facing values such as account_number, document_number, invoice_number, tag_names, or contact names when supported."
    )


class AccountActionInput(AccountNumberInput):
    action: enum_or_str(AccountAction) = Field(
        description="Action to run on the selected resource."
    )


class AccountRetrieveInput(BusinessContextInput):
    tool_handle: str = Field(
        description="Value copied from bookkeeping_accounts_list.items[].tool_handle. Pass it unchanged to bookkeeping_account_retrieve; do not use account numbers or database IDs here."
    )


class AccountListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to bookkeeping_account_retrieve. Do not edit or derive it from user-facing numbers.",
    )
    number: int | None = Field(
        default=None, description="Bookkeeping account number visible to the user."
    )
    name: str | None = Field(default=None, description="Display name.")
    type: enum_or_str(AccountType) | None = Field(
        default=None, description="Type/category shown for this record."
    )
    is_shown: bool | None = Field(
        default=None, description="Whether the account is visible."
    )
    is_used: bool | None = Field(
        default=None, description="Whether the account already has posted entries."
    )

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("bookkeeping_account", raw_id)
        return data


class AccountSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from bookkeeping_accounts_list.items[].tool_handle and pass it unchanged to bookkeeping_account_retrieve.",
    )
    number: int | None = Field(
        default=None, description="Bookkeeping account number visible to the user."
    )
    name: str | None = Field(default=None, description="Display name.")
    type: enum_or_str(AccountType) | None = Field(
        default=None,
        description="Type/category shown for this record.",
    )
    description: str | None = Field(
        default=None, description="Description text for this record."
    )
    is_shown: bool | None = Field(
        default=None,
        description="True for accounts visible in normal account selection lists.",
    )
    is_used: bool | None = Field(
        default=None, description="True for accounts that have entries posted to them."
    )
    balance: Any | None = Field(
        default=None, description="Current balance shown for this record."
    )
    header_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("header_id", "header"),
        description="Header ID for this account. Use bookkeeping_header_retrieve to expand this ID.",
    )
    header_path: Any | None = Field(
        default=None,
        description="Header hierarchy path for this account when account headers are enabled.",
    )
    default_vat_code: Any | None = Field(
        default=None,
        description="VAT code NoCFO uses by default for this account when applicable. To see valid VAT codes, call constants_retrieve with kind=vat_codes.",
    )
    default_vat_rate: Any | None = Field(
        default=None,
        description="VAT rate NoCFO uses by default for this account when applicable. To see valid/effective VAT rates, call constants_retrieve with kind=vat_rates (date_at required).",
    )

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_id = data.get("id")
        if "tool_handle" not in data and isinstance(raw_id, int):
            data["tool_handle"] = tool_handle("bookkeeping_account", raw_id)
        return data
