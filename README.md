<div align="center">

<img src="assets/banner.svg" alt="NoCFO AI Toolkit" width="100%" />

<br />

### Give AI assistants full access to Finnish bookkeeping, invoicing, and business data.

[![PyPI](https://img.shields.io/pypi/v/nocfo-cli)](https://pypi.org/project/nocfo-cli/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-%230073E6)](https://pypi.org/project/nocfo-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-%230073E6)](LICENSE)

</div>

Open-source Python toolkit that connects [NoCFO](https://nocfo.io) to your terminal and AI workflows — a single package powering a CLI client, an MCP server, and a Cursor AI skill.

## What You Can Ask

After connecting, you can ask your AI assistant things like:

- "How many sales invoices do I have this month?"
- "Who are my top 10 customers by revenue this year?"
- "Show unpaid invoices due this week."
- "List bookkeeping documents from January."
- "What was my VAT total last quarter?"

## Why This Is Useful

- One connection gives your AI assistant direct access to NoCFO business data
- No need to manually export CSV files for common questions
- Works for both non-technical users and developers

## Fastest Setup (Hosted MCP)

Use the hosted endpoint `mcp.nocfo.io` when your AI client supports remote MCP connectors.

### Connect to Claude

1. Open Claude settings and go to **Connectors / MCP**.
2. Add a new connector.
3. Enter server URL: `mcp.nocfo.io`
4. Sign in with your NoCFO account when prompted.
5. Open a new chat and test:
   - "List my businesses"
   - "Show this month's sales invoices"

### Connect to ChatGPT

If your ChatGPT plan includes MCP/custom connectors:

1. Open ChatGPT settings and go to **Connectors / Integrations**.
2. Add a custom MCP connector.
3. Set server URL to `mcp.nocfo.io`
4. Complete sign-in flow with your NoCFO account.
5. Test with:
   - "List my contacts"
   - "Show unpaid purchase invoices"

> If your workspace does not yet show MCP/custom connector options, use the local setup below with Claude Desktop or Cursor.

---

## Local Setup (Claude Desktop)

Use this when you want to run MCP locally on your machine.

### 1) Install the toolkit

```bash
pip install nocfo-cli
```

Alternative (no permanent install):

```bash
uvx nocfo-cli --help
```

### 2) Create NoCFO API token

1. Open [login.nocfo.io/auth/tokens](https://login.nocfo.io/auth/tokens/)
2. Click **Luo uusi avain** / **Create new key**
3. Name it (for example: `Claude Desktop`)
4. Copy the token and save it to a password manager

### 3) Add NoCFO MCP to Claude config

Open Claude Desktop config and add:

```json
{
  "mcpServers": {
    "nocfo": {
      "command": "uvx",
      "args": ["--from", "nocfo-cli", "nocfo", "mcp"],
      "env": {
        "NOCFO_JWT_TOKEN": "your_jwt_here"
      }
    }
  }
}
```

Then restart Claude Desktop.

<details>
<summary>Claude config file locations</summary>

| OS      | Path                                                              |
| ------- | ----------------------------------------------------------------- |
| Mac     | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                     |

</details>

## Local Setup (Cursor)

Add the following to your Cursor MCP config (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "nocfo": {
      "command": "uvx",
      "args": ["--from", "nocfo-cli", "nocfo", "mcp"],
      "env": {
        "NOCFO_JWT_TOKEN": "your_jwt_here"
      }
    }
  }
}
```

Then test with a simple prompt like "List my businesses".

---

## CLI Quick Examples

```bash
nocfo user me
nocfo businesses list
nocfo invoices list --business <business_slug>
nocfo reports balance-sheet --business <business_slug> --date-at 2026-12-31
nocfo reports balance-sheet-short --business <business_slug> --date-at 2026-12-31
nocfo reports income-statement --business <business_slug> --date-from 2026-01-01 --date-to 2026-12-31
nocfo reports income-statement-short --business <business_slug> --date-from 2026-01-01 --date-to 2026-12-31
nocfo reports ledger --business <business_slug> --date-from 2026-01-01 --date-to 2026-01-31
nocfo reports journal --business <business_slug> --date-from 2026-01-01 --date-to 2026-01-31
nocfo reports vat --business <business_slug> --date-from 2026-01-01 --date-to 2026-01-31
nocfo reports equity-changes --business <business_slug> --date-at 2026-12-31
```

JSON output:

```bash
nocfo --output json businesses list
```

## Advanced / Technical

### MCP tool surface

The MCP server exposes a curated workflow surface instead of mirroring the
backend API one-to-one. Tool names keep the NoCFO namespaces (`common_*`,
`bookkeeping_*`, `invoicing_*`, `reporting_*`, `constants_*`, `docs_*`), but
arguments prefer user-facing identifiers:

- use account numbers such as `1910`, not account IDs
- use document and invoice numbers when users refer to documents or invoices
- use tag names and contact names/emails for search and filtering
- use `business="current"` unless the user explicitly chooses another business

List tools return Linear-style pagination with `limit` and opaque `cursor`
arguments. Responses include `page_info.has_next_page` and
`page_info.next_cursor`.

Permission checks are not exposed as planning tools. If an API call is rejected,
the MCP returns a structured error with `error_type`, `message`, `hint`, and,
when available for `403`, the current user's permissions for that business.

For bookkeeping documents, `blueprint` means the editable posting plan used for
create/update workflows. `entries` are the realized journal lines generated from
the blueprint and are read-only through MCP. Use `docs_blueprint` for a concise
schema guide before mutating document bookkeeping.

### MCP server modes

- `nocfo mcp` = local stdio mode
- `nocfo mcp --transport http --auth-mode oauth --mcp-base-url mcp.nocfo.io` = remote HTTP mode
- Local stdio auth order: `NOCFO_JWT_TOKEN` first, then `NOCFO_API_TOKEN`
- `NOCFO_API_TOKEN` is optional for stdio when `NOCFO_JWT_TOKEN` is set

Detailed auth contract and troubleshooting are in `MCP_AUTHENTICATION.md`.

### Auth precedence

| Priority | Source                            |
| -------- | --------------------------------- |
| 1        | `--api-token` CLI flag            |
| 2        | `NOCFO_API_TOKEN` env var         |
| 3        | `~/.config/nocfo-cli/config.json` |

Default base URL: `https://api-prd.nocfo.io`
Default output format: `table`

## CLI Command Groups

| Group               | Description                              |
| ------------------- | ---------------------------------------- |
| `auth`              | Configure and verify authentication      |
| `businesses`        | List and manage businesses               |
| `accounts`          | Chart of accounts                        |
| `documents`         | Accounting entries and journal documents |
| `contacts`          | Customer and supplier contacts           |
| `invoices`          | Sales invoices                           |
| `purchase-invoices` | Purchase invoices                        |
| `products`          | Invoicing products                       |
| `files`             | File attachments                         |
| `tags`              | Document tags                            |
| `user`              | Current user info                        |
| `mcp`               | Start MCP server                         |

## Development

```bash
poetry install                # install dependencies
poetry run pytest             # run tests
poetry run nocfo --help       # run CLI locally
```

<details>
<summary>Publishing to PyPI</summary>

```bash
poetry build
poetry config pypi-token.pypi <pypi_token>
poetry publish
```

For TestPyPI:

```bash
poetry config repositories.testpypi https://test.pypi.org/legacy/
poetry config pypi-token.testpypi <testpypi_token>
poetry publish -r testpypi
```

</details>

## Security

- Never commit PAT tokens
- Keep `.env` local only
- Use separate tokens for test and production
- Local config contains secrets — do not share

## License

MIT — see [LICENSE](LICENSE).
