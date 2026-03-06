---
name: nocfo
description: Use NoCFO CLI for bookkeeping, invoicing, and business data operations. Use when the user wants to query or update NoCFO data from an agent through terminal commands.
---

# NoCFO CLI Skill

## Purpose

This skill helps an agent use the `nocfo` terminal client efficiently for NoCFO API operations.

## Prerequisites

1. Install CLI:
   - `pip install nocfo-cli`
2. Configure authentication:
   - `nocfo auth configure --token <token>`
3. Verify:
   - `nocfo auth status`

Environment variables:

- `NOCFO_API_TOKEN`
- `NOCFO_BASE_URL` (default `https://api-prd.nocfo.io`)
- `NOCFO_OUTPUT_FORMAT` (`table` or `json`)

## Command Structure

Pattern:

- `nocfo <group> <action> [options]`

Main groups:

- `auth`
- `businesses`
- `accounts`
- `documents`
- `contacts`
- `invoices`
- `purchase-invoices`
- `products`
- `files`
- `tags`
- `user`
- `mcp`

## Common Workflows

### 1) Check current user and businesses

```bash
nocfo user me
nocfo businesses list
```

### 2) List invoices for a business

```bash
nocfo invoices list --business my-business --query status=PAID
```

### 3) Create or update resources

Use either repeated `--field` pairs or `--json-body`.

```bash
nocfo contacts create --business my-business --field name=Example --field is_invoicing_enabled=true
nocfo products update 123 --business my-business --field name=UpdatedName --partial
```

### 4) Document and account operations

```bash
nocfo documents list --business my-business --query date_from=2026-01-01
nocfo accounts get 1910 --business my-business
```

### 5) File upload

```bash
nocfo files upload ./invoice.pdf --business my-business
```

## Error Handling

- If command fails with auth errors, run `nocfo auth status` and refresh token.
- If endpoint or payload fails, retry with `--output json` to inspect exact response.
- Prefer idempotent reads first (`list`, `get`) before writes (`create`, `update`, `delete`).

## MCP Usage

To run local MCP server for Claude/Cursor integration:

```bash
nocfo mcp
```

Example Claude Desktop server config:

```json
{
  "mcpServers": {
    "nocfo": {
      "command": "uvx",
      "args": ["nocfo-cli", "mcp"],
      "env": {
        "NOCFO_API_TOKEN": "your-token"
      }
    }
  }
}
```
