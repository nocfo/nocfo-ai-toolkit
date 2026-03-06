# MCP Authentication Contract (Claude + OpenAI)

This document describes the implemented auth flow for running `nocfo mcp` in remote OAuth mode.

## Token Exchange Contract

- Incoming connector request must include `Authorization: Bearer <oauth_access_token>`.
- MCP server validates bearer tokens with FastMCP `RemoteAuthProvider`:
  - Protected resource metadata is exposed through `/.well-known/oauth-protected-resource`.
  - OAuth authorization server URLs are advertised via `NOCFO_MCP_AUTHORIZATION_SERVERS` (or fallback: `<NOCFO_BASE_URL>/auth`).
- For downstream NoCFO API calls, MCP exchanges the incoming bearer with `POST /auth/jwt/` on backend:
  - request: `Authorization: Bearer <oauth_access_token>`, JSON body `{}`.
  - response: `{"token": "<short_lived_jwt>"}`.
  - `business_slug` is not sent (unscoped JWT only).
- MCP then calls NoCFO APIs with:
  - `Authorization: Token <jwt>`.

## Tool Auth Signaling

In OAuth mode, generated MCP tools include metadata:

- `securitySchemes`: `[{"type": "oauth2", "scopes": [...]?}]`
- `mcp/www_authenticate`: `"Bearer"`

This allows connector UIs to detect auth requirements and trigger linking flows.

## CLI Usage

```bash
nocfo mcp \
  --transport http \
  --auth-mode oauth \
  --mcp-base-url mcp.nocfo.io \
  --path /mcp
```

Required env for OAuth mode:

- `NOCFO_MCP_BASE_URL` (or `--mcp-base-url`)
- verifier mode (one of):
  - JWT verifier:
    - `NOCFO_MCP_TOKEN_VERIFIER=jwt` (default)
    - `NOCFO_MCP_JWKS_URI`
    - optional: `NOCFO_MCP_JWT_ISSUER`
    - optional: `NOCFO_MCP_JWT_AUDIENCE` (comma separated)
  - Introspection verifier:
    - `NOCFO_MCP_TOKEN_VERIFIER=introspection`
    - `NOCFO_MCP_INTROSPECTION_URL`
    - `NOCFO_MCP_INTROSPECTION_CLIENT_ID`
    - `NOCFO_MCP_INTROSPECTION_CLIENT_SECRET`
    - optional: `NOCFO_MCP_INTROSPECTION_CLIENT_AUTH_METHOD` (`client_secret_basic` or `client_secret_post`)

Optional:

- `NOCFO_MCP_REQUIRED_SCOPES` (comma separated)
- `NOCFO_MCP_AUTHORIZATION_SERVERS` (comma separated)

## Auth Error Mapping

- Missing bearer token in MCP request:
  - MCP rejects request with auth failure before downstream API call.
- `/auth/jwt/` exchange returns `401`:
  - treated as invalid/missing bearer for exchange.
- `/auth/jwt/` exchange returns `403`:
  - treated as authenticated but unauthorized exchange.
- `/auth/jwt/` exchange returns `5xx`:
  - treated as backend auth service failure.
- Exchanged JWT near expiry:
  - cache entry is refreshed before expiry using refresh skew (`60s` default).

## Operational Notes

- Bearer and JWT values are never written to logs by toolkit auth code.
- JWT exchange cache key is derived from token subject claim (fallback: bearer hash).
- Cache stores exchanged JWT per subject and refreshes it on demand near expiry.
