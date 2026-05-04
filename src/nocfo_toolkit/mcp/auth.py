"""Authentication helpers for remote NoCFO MCP deployments."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx
from fastmcp.server.auth import AccessToken, RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token, get_http_headers
from fastmcp.utilities.components import FastMCPComponent
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from nocfo_toolkit.config import AUTH_HEADER_SCHEME, ToolkitConfig

logger = logging.getLogger(__name__)


class MCPAuthConfigurationError(RuntimeError):
    """Raised when MCP auth env configuration is incomplete."""


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _incoming_mcp_client() -> str | None:
    headers = get_http_headers(include={"x-nocfo-client"})
    nocfo_client = (headers.get("x-nocfo-client") or "").strip()
    return nocfo_client or None


@dataclass(frozen=True)
class MCPAuthOptions:
    """Runtime auth settings used by the MCP server."""

    mode: Literal["pat", "oauth"] = "pat"
    mcp_base_url: str | None = None
    jwt_exchange_path: str = "/auth/jwt/"
    token_refresh_skew_seconds: int = 60
    required_scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RemoteOAuthConfig:
    """OAuth verifier + metadata configuration for remote MCP auth."""

    authorization_servers: tuple[str, ...]
    verifier_mode: Literal["jwt", "introspection", "userinfo"]
    jwt_jwks_uri: str | None
    jwt_issuer: str | None
    jwt_audience: tuple[str, ...]
    introspection_url: str | None
    introspection_client_id: str | None
    introspection_client_secret: str | None
    introspection_client_auth_method: Literal[
        "client_secret_basic", "client_secret_post"
    ]
    userinfo_url: str | None
    required_scopes: tuple[str, ...]

    @classmethod
    def from_env(cls, config: ToolkitConfig) -> RemoteOAuthConfig:
        verifier_mode = (_env("NOCFO_MCP_TOKEN_VERIFIER") or "jwt").lower()
        if verifier_mode not in {"jwt", "introspection", "userinfo"}:
            raise MCPAuthConfigurationError(
                "NOCFO_MCP_TOKEN_VERIFIER must be 'jwt', 'introspection', or "
                "'userinfo'."
            )

        authorization_servers = tuple(
            _split_csv(_env("NOCFO_MCP_AUTHORIZATION_SERVERS"))
            or [config.base_url.rstrip("/")]
        )
        required_scopes = tuple(_split_csv(_env("NOCFO_MCP_REQUIRED_SCOPES")))
        jwt_audience = tuple(_split_csv(_env("NOCFO_MCP_JWT_AUDIENCE")))

        verifier_mode_typed = cast(
            Literal["jwt", "introspection", "userinfo"],
            verifier_mode,
        )
        introspection_client_auth_method = (
            _env("NOCFO_MCP_INTROSPECTION_CLIENT_AUTH_METHOD") or "client_secret_basic"
        )
        if introspection_client_auth_method not in {
            "client_secret_basic",
            "client_secret_post",
        }:
            raise MCPAuthConfigurationError(
                "NOCFO_MCP_INTROSPECTION_CLIENT_AUTH_METHOD must be "
                "'client_secret_basic' or 'client_secret_post'."
            )
        return cls(
            authorization_servers=authorization_servers,
            verifier_mode=verifier_mode_typed,
            jwt_jwks_uri=_env("NOCFO_MCP_JWKS_URI"),
            jwt_issuer=_env("NOCFO_MCP_JWT_ISSUER"),
            jwt_audience=jwt_audience,
            introspection_url=_env("NOCFO_MCP_INTROSPECTION_URL"),
            introspection_client_id=_env("NOCFO_MCP_INTROSPECTION_CLIENT_ID"),
            introspection_client_secret=_env("NOCFO_MCP_INTROSPECTION_CLIENT_SECRET"),
            introspection_client_auth_method=cast(
                Literal["client_secret_basic", "client_secret_post"],
                introspection_client_auth_method,
            ),
            userinfo_url=_env("NOCFO_MCP_USERINFO_URL")
            or f"{config.base_url.rstrip('/')}/identity/o/api/userinfo",
            required_scopes=required_scopes,
        )

    def build_verifier(self):
        if self.verifier_mode == "jwt":
            if not self.jwt_jwks_uri:
                raise MCPAuthConfigurationError(
                    "Missing NOCFO_MCP_JWKS_URI for JWT verifier mode."
                )
            jwt_verifier = JWTVerifier(
                jwks_uri=self.jwt_jwks_uri,
                issuer=self.jwt_issuer,
                audience=list(self.jwt_audience) if self.jwt_audience else None,
                required_scopes=list(self.required_scopes) or None,
            )
            if self.userinfo_url:
                return FallbackTokenVerifier(
                    primary=jwt_verifier,
                    secondary=UserInfoTokenVerifier(
                        userinfo_url=self.userinfo_url,
                        required_scopes=list(self.required_scopes) or None,
                    ),
                )
            return jwt_verifier

        if self.verifier_mode == "userinfo":
            if not self.userinfo_url:
                raise MCPAuthConfigurationError(
                    "Missing NOCFO_MCP_USERINFO_URL for userinfo verifier mode."
                )
            return UserInfoTokenVerifier(
                userinfo_url=self.userinfo_url,
                required_scopes=list(self.required_scopes) or None,
            )

        if not self.introspection_url:
            raise MCPAuthConfigurationError(
                "Missing NOCFO_MCP_INTROSPECTION_URL for introspection verifier mode."
            )
        if not self.introspection_client_id or not self.introspection_client_secret:
            raise MCPAuthConfigurationError(
                "Missing introspection credentials: "
                "NOCFO_MCP_INTROSPECTION_CLIENT_ID and "
                "NOCFO_MCP_INTROSPECTION_CLIENT_SECRET are required."
            )
        return IntrospectionTokenVerifier(
            introspection_url=self.introspection_url,
            client_id=self.introspection_client_id,
            client_secret=self.introspection_client_secret,
            client_auth_method=self.introspection_client_auth_method,
            required_scopes=list(self.required_scopes) or None,
            cache_ttl_seconds=30,
        )


class UserInfoTokenVerifier(TokenVerifier):
    """Validate opaque OAuth access tokens via OIDC userinfo endpoint."""

    def __init__(
        self, *, userinfo_url: str, required_scopes: list[str] | None = None
    ) -> None:
        super().__init__(required_scopes=required_scopes)
        self._userinfo_url = userinfo_url

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    self._userinfo_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            logger.info(
                "OAuth userinfo token verification failed transport_error=%s",
                type(exc).__name__,
            )
            return None

        if response.status_code != 200:
            logger.info(
                "OAuth userinfo token verification failed status=%s detail=%s",
                response.status_code,
                _extract_error_detail(response),
            )
            return None

        payload = response.json() if response.content else {}
        if not isinstance(payload, dict):
            return None

        # allauth returns opaque access tokens; if scopes are not explicitly
        # included in userinfo payload, treat configured required scopes as granted.
        scope_value = payload.get("scope")
        scopes = (
            [s for s in scope_value.split(" ") if s]
            if isinstance(scope_value, str) and scope_value.strip()
            else list(self.required_scopes or [])
        )
        if self.required_scopes and not set(self.required_scopes).issubset(set(scopes)):
            return None

        client_id = payload.get("azp") or payload.get("client_id") or "nocfo-userinfo"
        return AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=scopes,
            claims=payload,
        )


class FallbackTokenVerifier(TokenVerifier):
    """Try primary verifier first, then fall back to secondary verifier."""

    def __init__(self, *, primary: TokenVerifier, secondary: TokenVerifier) -> None:
        super().__init__(required_scopes=primary.required_scopes)
        self._primary = primary
        self._secondary = secondary

    async def verify_token(self, token: str) -> AccessToken | None:
        primary_result = await self._primary.verify_token(token)
        if primary_result is not None:
            return primary_result
        return await self._secondary.verify_token(token)


class JwtExchangeAuth(httpx.Auth):
    """Exchange incoming OAuth bearer to NoCFO JWT for downstream API calls."""

    requires_request_body = True

    def __init__(
        self,
        *,
        exchange_path: str = "/auth/jwt/",
        refresh_skew_seconds: int = 60,
    ) -> None:
        self._exchange_path = (
            exchange_path if exchange_path.startswith("/") else f"/{exchange_path}"
        )
        self._refresh_skew_seconds = max(0, refresh_skew_seconds)
        self._cache: dict[str, tuple[str, int | None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _cache_key(access_token: str, claims: dict[str, Any]) -> str:
        stable_id = claims.get("sub") or claims.get("user_id") or claims.get("uid")
        if stable_id:
            return str(stable_id)
        return hashlib.sha256(access_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode_exp(jwt_token: str) -> int | None:
        try:
            parts = jwt_token.split(".")
            if len(parts) != 3:
                return None
            payload = parts[1]
            padding = "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
            parsed = json.loads(decoded)
            value = parsed.get("exp")
            return int(value) if value is not None else None
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _is_fresh(self, expires_at: int | None) -> bool:
        if expires_at is None:
            return True
        return time.time() < float(expires_at - self._refresh_skew_seconds)

    def _get_lock(self, cache_key: str) -> asyncio.Lock:
        lock = self._locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[cache_key] = lock
        return lock

    async def async_auth_flow(self, request: httpx.Request):
        access = get_access_token()
        bearer_token = access.token if access else None
        if not bearer_token:
            raise RuntimeError("Missing OAuth bearer token for MCP request.")
        incoming_nocfo_client = _incoming_mcp_client()

        claims = access.claims if access and isinstance(access.claims, dict) else {}
        cache_key = self._cache_key(bearer_token, claims)
        cached = self._cache.get(cache_key)
        jwt_token = cached[0] if cached and self._is_fresh(cached[1]) else None

        if jwt_token is None:
            lock = self._get_lock(cache_key)
            async with lock:
                cached = self._cache.get(cache_key)
                jwt_token = cached[0] if cached and self._is_fresh(cached[1]) else None
                if jwt_token is None:
                    exchange_request = httpx.Request(
                        method="POST",
                        url=request.url.copy_with(path=self._exchange_path, query=b""),
                        headers={
                            "Authorization": f"Bearer {bearer_token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            **(
                                {"x-nocfo-client": incoming_nocfo_client}
                                if incoming_nocfo_client
                                else {}
                            ),
                        },
                        content=b"{}",
                    )

                    exchange_response = yield exchange_request
                    await exchange_response.aread()
                    if exchange_response.status_code >= 400:
                        detail = _extract_error_detail(exchange_response)
                        logger.warning(
                            "JWT exchange failed status=%s detail=%s",
                            exchange_response.status_code,
                            detail,
                        )
                    if exchange_response.status_code == 401:
                        raise RuntimeError(
                            "JWT exchange failed: incoming bearer token is missing or "
                            f"invalid. {_format_error_detail(exchange_response)}"
                        )
                    if exchange_response.status_code == 403:
                        raise RuntimeError(
                            "JWT exchange failed: authenticated user is not allowed to "
                            f"get JWT. {_format_error_detail(exchange_response)}"
                        )
                    if exchange_response.status_code >= 500:
                        raise RuntimeError(
                            "JWT exchange failed due to backend server error. "
                            f"{_format_error_detail(exchange_response)}"
                        )
                    if exchange_response.status_code >= 400:
                        raise RuntimeError(
                            "JWT exchange failed with status "
                            f"{exchange_response.status_code}. "
                            f"{_format_error_detail(exchange_response)}"
                        )

                    payload = exchange_response.json()
                    value = payload.get("token") if isinstance(payload, dict) else None
                    if not isinstance(value, str) or not value:
                        raise RuntimeError(
                            "JWT exchange succeeded without token payload."
                        )
                    jwt_token = value
                    self._cache[cache_key] = (jwt_token, self._decode_exp(jwt_token))

        request.headers["Authorization"] = f"{AUTH_HEADER_SCHEME} {jwt_token}"
        if incoming_nocfo_client:
            request.headers["x-nocfo-client"] = incoming_nocfo_client
        yield request


class PassthroughAuth(httpx.Auth):
    """Forward incoming HTTP Authorization header to downstream API requests."""

    async def async_auth_flow(self, request: httpx.Request):
        headers = get_http_headers(include={"authorization", "x-nocfo-client"})
        authorization = headers.get("authorization")
        if not authorization:
            raise RuntimeError("Missing Authorization header for MCP passthrough mode.")
        request.headers["Authorization"] = authorization
        nocfo_client = (headers.get("x-nocfo-client") or "").strip()
        if nocfo_client:
            request.headers["x-nocfo-client"] = nocfo_client
        yield request


def _extract_error_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json() if response.content else None
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in (
            "detail",
            "message",
            "error_description",
            "error_message",
            "error",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        if "non_field_errors" in payload and isinstance(
            payload["non_field_errors"], list
        ):
            return "; ".join(
                item.strip()
                for item in payload["non_field_errors"]
                if isinstance(item, str) and item.strip()
            )

    text = response.text.strip() if response.text else ""
    return text or None


def _format_error_detail(response: httpx.Response) -> str:
    detail = _extract_error_detail(response)
    return f"Reason: {detail}" if detail else "Reason unavailable."


class _CleanUrlAuthProvider(RemoteAuthProvider):
    """RemoteAuthProvider that strips Pydantic AnyHttpUrl trailing slashes.

    Pydantic v2 normalises bare-host URLs (``https://host`` →
    ``https://host/``).  MCP clients concatenate this with
    ``/.well-known/…`` paths, producing double-slash URLs that 404 on
    most identity providers.  This subclass wraps the protected-resource
    metadata route so the serialised JSON contains slash-free URLs.
    """

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        routes = super().get_routes(mcp_path)
        return [self._clean_metadata_route(r) for r in routes]

    @staticmethod
    def _strip_slashes_from_metadata_body(body: dict[str, Any]) -> dict[str, Any]:
        for key in ("resource", "authorization_servers"):
            val = body.get(key)
            if isinstance(val, str):
                body[key] = val.rstrip("/")
            elif isinstance(val, list):
                body[key] = [
                    str(item).rstrip("/") if item is not None else item for item in val
                ]
        return body

    @staticmethod
    def _clean_metadata_route(route: Route) -> Route:
        if "oauth-protected-resource" not in (route.path or ""):
            return route

        original = route.endpoint
        try:
            signature_params = len(inspect.signature(original).parameters)
        except (TypeError, ValueError):
            return route

        if signature_params == 1:

            async def _strip_trailing_slashes(request):  # type: ignore[no-untyped-def]
                response = await original(request)
                body = json.loads(response.body)
                cleaned = _CleanUrlAuthProvider._strip_slashes_from_metadata_body(body)
                return JSONResponse(cleaned, headers=dict(response.headers))

            wrapped_endpoint = _strip_trailing_slashes
        elif signature_params == 3:

            async def _strip_trailing_slashes_from_asgi(  # type: ignore[no-untyped-def]
                request,
            ):
                start_message: dict[str, Any] | None = None
                body_chunks: list[bytes] = []

                async def _capture_send(message: dict[str, Any]) -> None:
                    nonlocal start_message
                    message_type = message.get("type")
                    if message_type == "http.response.start":
                        start_message = dict(message)
                        return
                    if message_type == "http.response.body":
                        body_chunks.append(message.get("body", b""))

                await original(request.scope, request.receive, _capture_send)
                response_body = b"".join(body_chunks)
                transformed_body = response_body
                status_code = 200
                headers_dict: dict[str, str] = {}

                if start_message is not None:
                    status_code = int(start_message.get("status", 200))
                    headers = MutableHeaders(raw=start_message.get("headers", []))
                    content_type = headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            parsed_body = json.loads(response_body.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            parsed_body = None
                        if isinstance(parsed_body, dict):
                            cleaned = (
                                _CleanUrlAuthProvider._strip_slashes_from_metadata_body(
                                    parsed_body
                                )
                            )
                            transformed_body = json.dumps(cleaned).encode("utf-8")
                            headers["content-length"] = str(len(transformed_body))
                    headers_dict = dict(headers.items())

                return Response(
                    content=transformed_body,
                    status_code=status_code,
                    headers=headers_dict,
                )

            wrapped_endpoint = _strip_trailing_slashes_from_asgi
        else:
            return route

        return Route(
            route.path,
            endpoint=wrapped_endpoint,
            methods=route.methods,
        )


def build_remote_auth_provider(
    *,
    config: ToolkitConfig,
    options: MCPAuthOptions,
) -> _CleanUrlAuthProvider:
    """Create a FastMCP RemoteAuthProvider for connector OAuth bearer verification."""

    if options.mode != "oauth":
        raise MCPAuthConfigurationError(
            "Remote auth provider can only be created in oauth mode."
        )
    if not options.mcp_base_url:
        raise MCPAuthConfigurationError(
            "Missing MCP public base URL. Set --mcp-base-url or "
            "NOCFO_MCP_BASE_URL for oauth mode."
        )

    remote = RemoteOAuthConfig.from_env(config)
    verifier = remote.build_verifier()
    return _CleanUrlAuthProvider(
        token_verifier=verifier,
        authorization_servers=list(remote.authorization_servers),
        base_url=options.mcp_base_url,
        scopes_supported=list(options.required_scopes or remote.required_scopes),
        resource_name="NoCFO MCP",
    )


def apply_tool_auth_metadata(
    component: FastMCPComponent, *, required_scopes: tuple[str, ...]
) -> None:
    """Attach explicit auth metadata so connector UIs can trigger linking flows.

    Applies to tools, resources, and resource templates exposed by MCP.
    """

    meta: dict[str, Any] = dict(component.meta or {})
    scheme: dict[str, Any] = {"type": "oauth2"}
    if required_scopes:
        scheme["scopes"] = list(required_scopes)
    meta["securitySchemes"] = [scheme]
    # Mirrors the MCP auth hint key expected by connector implementations.
    meta["mcp/www_authenticate"] = "Bearer"
    component.meta = meta
