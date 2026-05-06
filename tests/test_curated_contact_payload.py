from __future__ import annotations

from nocfo_toolkit.mcp.curated.invoicing.contact import (
    _build_contact_create_body,
    _build_contact_patch_body,
)
from nocfo_toolkit.mcp.curated.schema.invoicing.contact import (
    ContactCreateInput,
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
