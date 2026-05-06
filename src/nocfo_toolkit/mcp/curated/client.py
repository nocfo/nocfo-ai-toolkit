"""Curated NoCFO API client facade for MCP tools."""

from __future__ import annotations

from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from pydantic import BaseModel

from nocfo_toolkit.config import ToolkitConfig
from nocfo_toolkit.mcp.curated.errors import (
    error_type,
    field_errors,
    hint_for_status,
    message_from_payload,
    raise_tool_error,
)
from nocfo_toolkit.mcp.curated.schemas import (
    ListEnvelope,
    PageInfo,
    ResolvedBusiness,
    dump_model,
    dump_model_from_backend,
    dump_models,
)
from nocfo_toolkit.mcp.curated.utils import (
    b64_json,
    decode_tool_handle,
    encode_tool_handle,
    items,
    jwt_business_slug,
    parse_cursor,
    project,
    project_business,
)

HANDLE_RESOURCE_BY_PATH = (
    ("account/", "bookkeeping_account"),
    ("document/", "bookkeeping_document"),
    ("invoice/", "invoicing_sales_invoice"),
    ("purchase_invoice/", "invoicing_purchase_invoice"),
    ("contacts/", "invoicing_contact"),
    ("products/", "invoicing_product"),
    ("tags/", "bookkeeping_tag"),
    ("files/", "bookkeeping_file"),
    ("header/", "bookkeeping_header"),
    ("period/", "reporting_period"),
)


class CuratedNocfoClient:
    """Small MCP-facing facade over the NoCFO public API."""

    def __init__(self, client: httpx.AsyncClient, config: ToolkitConfig) -> None:
        self._client = client
        self._config = config

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        business_slug: str | None = None,
    ) -> Any:
        response = await self._client.request(
            method.upper(),
            path,
            params={k: v for k, v in (params or {}).items() if v is not None},
            json=json_body,
        )
        if response.status_code >= 400:
            await self._raise_response_error(response, business_slug=business_slug)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def request_multipart(
        self,
        path: str,
        *,
        files: dict[str, Any],
        business_slug: str | None = None,
    ) -> Any:
        response = await self._client.post(path, files=files)
        if response.status_code >= 400:
            await self._raise_response_error(response, business_slug=business_slug)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def _raise_response_error(
        self, response: httpx.Response, *, business_slug: str | None
    ) -> None:
        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {}
        message = (
            message_from_payload(payload) or response.text or "API request failed."
        )
        errors = field_errors(payload)
        permissions = None
        if response.status_code == 403 and business_slug:
            permissions = await self._permissions_for_error(business_slug)
        raise_tool_error(
            error_type(response.status_code),
            message,
            hint_for_status(response.status_code),
            status_code=response.status_code,
            field_errors=errors,
            current_permissions=permissions,
        )

    async def _permissions_for_error(self, business_slug: str) -> list[str] | None:
        try:
            payload = await self.request(
                "GET",
                f"/v1/business/{business_slug}/me/permissions/",
            )
        except ToolError:
            return None
        if isinstance(payload, dict):
            values = payload.get("granted_permission_ids")
            if isinstance(values, list):
                return [str(v) for v in values]
        return None

    async def resolve_business(self, business: str = "current") -> ResolvedBusiness:
        normalized_business = (business or "").strip()
        if normalized_business and normalized_business.lower() != "current":
            return ResolvedBusiness(slug=normalized_business, source="explicit")

        for candidate in (
            self._config.jwt_token,
            get_http_headers(include={"authorization"}).get("authorization"),
        ):
            if jwt_slug := jwt_business_slug(candidate):
                return ResolvedBusiness(slug=jwt_slug, source="jwt")

        businesses = await self.accessible_businesses(limit=25)
        if len(businesses) == 1:
            item = businesses[0]
            return ResolvedBusiness(
                slug=str(item.get("slug")),
                name=str(item.get("name") or ""),
                source="single_accessible_business",
            )

        raise_tool_error(
            "business_context_required",
            "No single current business could be resolved.",
            "Ask the user which business to use, then pass its slug as `business`.",
            candidates=[project_business(item) for item in businesses],
        )

    async def accessible_businesses(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = await self.request(
            "GET", "/v1/business/", params={"page_size": limit}
        )
        return items(payload)

    async def list_page(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        cursor: str | None = None,
        limit: int = 8,
        business_slug: str | None = None,
        fields: tuple[str, ...] = (),
        item_model: type[BaseModel] | None = None,
        usage_hint: str | None = None,
        handle_resource: str | None = None,
    ) -> dict[str, Any]:
        page = parse_cursor(cursor)

        query = dict(params or {})
        query["page"] = page
        query["page_size"] = min(max(int(limit), 1), 100)
        payload = await self.request(
            "GET", path, params=query, business_slug=business_slug
        )

        raw_items = items(payload)
        total_size = (
            payload.get("size") if isinstance(payload.get("size"), int) else None
        )
        next_cursor = b64_json({"page": page + 1}) if payload.get("next") else None
        projected = (
            dump_models(item_model, raw_items)
            if item_model is not None
            else [project(item, fields) for item in raw_items]
        )
        if handle_resource:
            for raw_item, item in zip(raw_items, projected, strict=False):
                raw_id = raw_item.get("id")
                if isinstance(raw_id, int):
                    item["tool_handle"] = encode_tool_handle(handle_resource, raw_id)
        resolved_usage_hint = usage_hint
        if total_size is not None:
            count_hint = "For total matches, use page_info.total_size."
            resolved_usage_hint = (
                f"{usage_hint} {count_hint}" if usage_hint else count_hint
            )

        envelope = ListEnvelope(
            items=projected,
            page_info=PageInfo(
                has_next_page=next_cursor is not None,
                next_cursor=next_cursor,
                limit=query["page_size"],
                total_size=total_size,
            ),
            usage_hint=resolved_usage_hint,
        )
        return dump_model(envelope)

    async def retrieve_by_lookup(
        self,
        list_path: str,
        detail_path_template: str,
        *,
        lookup_field: str,
        lookup_value: Any,
        params: dict[str, Any] | None = None,
        search_param: str | None = None,
        business_slug: str,
        fields: tuple[str, ...] = (),
        item_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        query = dict(params or {})
        if search_param:
            query[search_param] = lookup_value
        else:
            query[lookup_field] = lookup_value
        payload = await self.request(
            "GET",
            list_path,
            params={**query, "page_size": 10 if search_param else 3},
            business_slug=business_slug,
        )
        candidates = items(payload)
        if search_param:
            candidates = [
                item for item in candidates if item.get(lookup_field) == lookup_value
            ]
        if not candidates:
            raise_tool_error(
                "not_found",
                f"No record found for {lookup_field}={lookup_value}.",
                "Use the corresponding list tool to search and disambiguate.",
            )
        if len(candidates) > 1:
            raise_tool_error(
                "ambiguous_reference",
                f"Multiple records matched {lookup_field}={lookup_value}.",
                "Use the candidates to choose the right record, then call again with an exact identifier.",
                candidates=[
                    dump_model_from_backend(item_model, item)
                    if item_model is not None
                    else project(item, fields)
                    for item in candidates
                ],
            )
        item_id = candidates[0].get("id")
        detail = await self.request(
            "GET",
            detail_path_template.format(id=item_id),
            business_slug=business_slug,
        )
        detail_data = detail if isinstance(detail, dict) else {}
        if item_model is not None:
            return dump_model_from_backend(item_model, detail_data)
        return project(detail_data, fields)

    async def resolve_id(
        self,
        list_path: str,
        *,
        lookup_field: str,
        lookup_value: Any,
        business_slug: str,
        search_param: str | None = None,
    ) -> int:
        query = {lookup_field: lookup_value}
        if search_param:
            query = {search_param: lookup_value}
        payload = await self.request(
            "GET",
            list_path,
            params={**query, "page_size": 3},
            business_slug=business_slug,
        )
        candidates = items(payload)
        exact = [
            item
            for item in candidates
            if str(item.get(lookup_field) or "").lower() == str(lookup_value).lower()
        ]
        candidates = exact or candidates
        if len(candidates) != 1:
            resource = _resource_from_path(list_path)
            raise_tool_error(
                "ambiguous_reference" if candidates else "not_found",
                f"Could not resolve {lookup_field}={lookup_value}.",
                _resolve_id_hint(list_path),
                candidates=[
                    _compact_candidate(
                        item=item,
                        lookup_field=lookup_field,
                        resource=resource,
                    )
                    for item in candidates
                ],
            )
        return int(candidates[0]["id"])

    async def resolve_exact_id(
        self,
        *,
        tool_handle: str | None,
        internal_id: int | None,
        expected_resource: str,
        id_field_name: str,
    ) -> int:
        if (tool_handle is None and internal_id is None) or (
            tool_handle is not None and internal_id is not None
        ):
            raise_tool_error(
                "invalid_request",
                f"Provide exactly one of tool_handle or {id_field_name}.",
                f"Call a matching *_list tool first, then pass its tool_handle or explicit {id_field_name}.",
                status_code=400,
            )
        if tool_handle is not None:
            return decode_tool_handle(tool_handle, expected_resource=expected_resource)
        assert internal_id is not None
        return int(internal_id)

    def require_numeric_identifier(self, identifier: str, *, field_name: str) -> int:
        value = str(identifier).strip()
        if not value.isdigit():
            raise_tool_error(
                "invalid_request",
                f"{field_name} must be a numeric ID.",
                f"Use a numeric {field_name} returned by the matching list tool.",
                status_code=400,
            )
        parsed = int(value)
        if parsed < 1:
            raise_tool_error(
                "invalid_request",
                f"{field_name} must be a positive integer.",
                f"Use a numeric {field_name} returned by the matching list tool.",
                status_code=400,
            )
        return parsed


def _resource_from_path(list_path: str) -> str | None:
    lowered = list_path.lower()
    for needle, resource in HANDLE_RESOURCE_BY_PATH:
        if needle in lowered:
            return resource
    return None


def _resolve_id_hint(list_path: str) -> str:
    if "/tags/" in list_path.lower():
        return (
            "If the tag name does not exist yet, create it first with "
            "bookkeeping_tag_create. Otherwise call bookkeeping_tags_list and pass "
            "items[].tool_handle unchanged to bookkeeping_tag_retrieve."
        )
    return "Call the matching list tool and pass items[].tool_handle unchanged to the retrieve tool."


def _compact_candidate(
    *, item: dict[str, Any], lookup_field: str, resource: str | None
) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    if resource and isinstance(item.get("id"), int):
        candidate["tool_handle"] = encode_tool_handle(resource, int(item["id"]))

    value = item.get(lookup_field)
    if value is not None:
        candidate[lookup_field] = value

    for display_field in ("name", "number", "invoice_number", "date", "start_date"):
        if display_field == lookup_field:
            continue
        display_value = item.get(display_field)
        if display_value is not None:
            candidate[display_field] = display_value
            break
    return candidate
