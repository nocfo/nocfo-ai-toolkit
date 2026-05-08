from __future__ import annotations

from nocfo_toolkit.mcp.curated.invoicing.contact import (
    _build_contact_create_body,
    _build_contact_patch_body,
)
from nocfo_toolkit.mcp.curated.schema.invoicing.contact import (
    ContactCreateInput,
    ContactSummary,
    ContactUpdateInput,
)


def test_build_contact_create_body_omits_none_values() -> None:
    params = ContactCreateInput.model_validate(
        {
            "name": "Test Contact",
            "email": "contact@example.com",
            "phone": None,
            "business": "current",
        }
    )

    body = _build_contact_create_body(params)
    assert body["name"] == "Test Contact"
    assert body["email"] == "contact@example.com"
    assert "phone" not in body


def test_build_contact_patch_body_preserves_explicit_nulls() -> None:
    params = ContactUpdateInput.model_validate(
        {
            "identifier": "123",
            "invoicing_email": None,
            "city": "Helsinki",
            "business": "current",
        }
    )

    body = _build_contact_patch_body(params)
    assert "invoicing_email" in body
    assert body["invoicing_email"] is None
    assert body["city"] == "Helsinki"
    assert "phone" not in body


def test_build_contact_create_body_includes_new_contact_fields() -> None:
    params = ContactCreateInput.model_validate(
        {
            "name": "Alias Contact",
            "phone_number": "+358401234567",
            "notes": "Priority customer",
            "name_aliases": ["A. Contact", "Alias Contact Oy"],
            "business": "current",
        }
    )

    body = _build_contact_create_body(params)
    assert body["phone_number"] == "+358401234567"
    assert body["notes"] == "Priority customer"
    assert body["name_aliases"] == ["A. Contact", "Alias Contact Oy"]


def test_build_contact_patch_body_includes_new_contact_fields() -> None:
    params = ContactUpdateInput.model_validate(
        {
            "identifier": "123",
            "phone_number": None,
            "notes": "Updated notes",
            "name_aliases": [],
            "business": "current",
        }
    )

    body = _build_contact_patch_body(params)
    assert "phone_number" in body
    assert body["phone_number"] is None
    assert body["notes"] == "Updated notes"
    assert body["name_aliases"] == []


def test_contact_summary_maps_new_contact_fields_from_backend_payload() -> None:
    summary = ContactSummary.model_validate(
        {
            "id": 2013,
            "name": "ABC-123",
            "name_aliases": ["ABC Group"],
            "notes": "VIP",
            "phone_number": None,
        }
    )

    assert summary.contact_id == 2013
    assert summary.name_aliases == ["ABC Group"]
    assert summary.notes == "VIP"
    assert summary.phone_number is None
