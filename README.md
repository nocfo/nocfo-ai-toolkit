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
      "args": ["nocfo-cli", "mcp"],
      "env": {
        "NOCFO_API_TOKEN": "your_token_here"
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

1. Open **Cursor → Settings → MCP → Add Server**
2. Use command: `nocfo mcp` (or `uvx nocfo-cli mcp`)
3. Add env var `NOCFO_API_TOKEN=<your_token>`
4. Save and test with a simple prompt like "List my businesses"

---

## CLI Quick Examples

```bash
nocfo user me
nocfo businesses list
nocfo invoices list --business <business_slug>
nocfo reports balance-sheet --business <business_slug> --date-to 2026-12-31
```

JSON output:

```bash
nocfo --output json businesses list
```

## Advanced / Technical

### MCP server modes

- `nocfo mcp` = local stdio mode
- `nocfo mcp --transport http --auth-mode oauth --mcp-base-url mcp.nocfo.io` = remote HTTP mode

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

Regenerate OpenAPI-based command stubs:

```bash
poetry run python scripts/generate_cli_commands.py
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
