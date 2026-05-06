"""Invoicing contact schemas."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, ConfigDict, Field, model_validator

from nocfo_toolkit.mcp.curated.schema.common import (
    AgentModel,
    BusinessContextInput,
    BusinessPaginationInput,
    ContactType,
    enum_or_str,
    tool_handle,
)


class ContactListInput(BusinessPaginationInput):
    contact_business_id: str | None = Field(
        default=None,
        description="Customer/contact identifier (asiakastunnus). Use this when the user gives an exact customer number.",
    )


class ContactRetrieveInput(BusinessContextInput):
    tool_handle: str | None = Field(
        default=None,
        description="Value copied from invoicing_contacts_list.items[].tool_handle. Pass it unchanged to invoicing_contact_retrieve.",
    )
    contact_id: int | None = Field(
        default=None, description="Internal contact ID when explicitly known."
    )

    @model_validator(mode="after")
    def validate_contact_selector(self) -> "ContactRetrieveInput":
        if (self.tool_handle is None and self.contact_id is None) or (
            self.tool_handle is not None and self.contact_id is not None
        ):
            raise ValueError("Provide exactly one of tool_handle or contact_id")
        return self


class ContactCreateInput(BusinessContextInput):
    name: str = Field(description="Display name.")
    type: enum_or_str(ContactType) | None = Field(
        default=None, description="Type/category shown for this record."
    )
    customer_id: str | int | None = Field(
        default=None, description="Customer identifier used in invoicing workflows."
    )
    contact_business_id: str | None = Field(
        default=None, description="Customer/contact identifier (asiakastunnus)."
    )
    invoicing_email: str | None = Field(
        default=None, description="Email address used for invoice delivery."
    )
    invoicing_electronic_address: str | None = Field(
        default=None, description="E-invoice address for the contact."
    )
    invoicing_einvoice_operator: str | None = Field(
        default=None, description="E-invoice operator for the contact."
    )
    invoicing_country: str | None = Field(
        default=None, description="Invoicing country code or value."
    )
    invoicing_language: str | None = Field(
        default=None, description="Preferred invoicing language."
    )
    email: str | None = Field(
        default=None, description="User or contact email address."
    )
    phone: str | None = Field(default=None, description="Contact phone number.")
    vat_number: str | None = Field(default=None, description="VAT number.")
    y_tunnus: str | None = Field(
        default=None, description="Finnish business ID (Y-tunnus)."
    )
    city: str | None = Field(default=None, description="Contact city.")
    country: str | None = Field(default=None, description="Contact country.")
    address: str | None = Field(default=None, description="Street address.")
    zip_code: str | None = Field(default=None, description="ZIP/postal code.")


class ContactUpdateInput(BusinessContextInput):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(
        description="Identifier for this resource. Prefer contact ID or exact contact name."
    )
    name: str | None = Field(default=None, description="Display name.")
    type: enum_or_str(ContactType) | None = Field(
        default=None, description="Type/category shown for this record."
    )
    customer_id: str | int | None = Field(
        default=None, description="Customer identifier used in invoicing workflows."
    )
    contact_business_id: str | None = Field(
        default=None, description="Customer/contact identifier (asiakastunnus)."
    )
    invoicing_email: str | None = Field(
        default=None, description="Email address used for invoice delivery."
    )
    invoicing_electronic_address: str | None = Field(
        default=None, description="E-invoice address for the contact."
    )
    invoicing_einvoice_operator: str | None = Field(
        default=None, description="E-invoice operator for the contact."
    )
    invoicing_country: str | None = Field(
        default=None, description="Invoicing country code or value."
    )
    invoicing_language: str | None = Field(
        default=None, description="Preferred invoicing language."
    )
    email: str | None = Field(
        default=None, description="User or contact email address."
    )
    phone: str | None = Field(default=None, description="Contact phone number.")
    vat_number: str | None = Field(default=None, description="VAT number.")
    y_tunnus: str | None = Field(
        default=None, description="Finnish business ID (Y-tunnus)."
    )
    city: str | None = Field(default=None, description="Contact city.")
    country: str | None = Field(default=None, description="Contact country.")
    address: str | None = Field(default=None, description="Street address.")
    zip_code: str | None = Field(default=None, description="ZIP/postal code.")

    @model_validator(mode="after")
    def validate_has_patch_fields(self) -> "ContactUpdateInput":
        updated_fields = self.model_fields_set - {"business", "identifier"}
        if not updated_fields:
            raise ValueError("Provide at least one field to update.")
        return self


class ContactSummary(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from invoicing_contacts_list.items[].tool_handle and pass it unchanged to invoicing_contact_retrieve.",
    )
    contact_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("contact_id", "id"),
        description="Internal contact ID for exact follow-up calls.",
    )
    name: str | None = Field(default=None, description="Display name.")
    type: enum_or_str(ContactType) | None = Field(
        default=None,
        description="Type/category shown for this record.",
    )
    customer_id: str | int | None = Field(
        default=None, description="Customer identifier used in invoicing workflows."
    )
    contact_business_id: str | None = Field(
        default=None, description="Customer/contact identifier (asiakastunnus)."
    )
    invoicing_email: str | None = Field(
        default=None, description="Email address used for invoice delivery."
    )
    invoicing_electronic_address: str | None = Field(
        default=None, description="E-invoice address for the contact."
    )
    invoicing_einvoice_operator: Any | None = Field(
        default=None, description="E-invoice operator for the contact."
    )
    invoicing_country: str | None = Field(
        default=None, description="Invoicing country code or value."
    )
    invoicing_language: str | None = Field(
        default=None, description="Preferred invoicing language."
    )
    can_be_invoiced: bool | None = Field(
        default=None, description="Whether the contact has enough data for invoicing."
    )
    can_be_invoiced_via_email: bool | None = Field(
        default=None, description="Whether invoices can be sent by email."
    )
    can_be_invoiced_via_einvoice: bool | None = Field(
        default=None, description="Whether invoices can be sent by e-invoice."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_contact_id(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "contact_id" not in data and isinstance(data.get("id"), int):
            data["contact_id"] = data["id"]
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "tool_handle" not in data and isinstance(data.get("contact_id"), int):
            data["tool_handle"] = tool_handle("invoicing_contact", data["contact_id"])
        return data


class ContactListItem(AgentModel):
    tool_handle: str | None = Field(
        default=None,
        description="Copy this value from items[].tool_handle and pass it unchanged to invoicing_contact_retrieve.",
    )
    contact_id: int | None = Field(
        default=None,
        validation_alias=AliasChoices("contact_id", "id"),
        description="Internal contact ID for exact follow-up calls.",
    )
    name: str | None = Field(default=None, description="Display name.")
    type: enum_or_str(ContactType) | None = Field(
        default=None, description="Type/category shown for this record."
    )
    contact_business_id: str | None = Field(
        default=None, description="Customer/contact identifier (asiakastunnus)."
    )
    invoicing_email: str | None = Field(
        default=None, description="Email address used for invoice delivery."
    )
    can_be_invoiced: bool | None = Field(
        default=None, description="Whether the contact has enough data for invoicing."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_contact_id(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "contact_id" not in data and isinstance(data.get("id"), int):
            data["contact_id"] = data["id"]
        return data

    @model_validator(mode="before")
    @classmethod
    def populate_tool_handle(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "tool_handle" not in data and isinstance(data.get("contact_id"), int):
            data["tool_handle"] = tool_handle("invoicing_contact", data["contact_id"])
        return data
