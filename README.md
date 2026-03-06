<div align="center">

<img src="assets/banner.svg" alt="NoCFO AI Toolkit" width="100%" />

<br />

### Give AI assistants full access to Finnish bookkeeping, invoicing, and business data.

[![PyPI](https://img.shields.io/badge/PyPI-v0.1.0-%230073E6)](https://pypi.org/project/nocfo-cli/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-%230073E6)](https://pypi.org/project/nocfo-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-%230073E6)](LICENSE)

</div>

Open-source Python toolkit that connects [NoCFO](https://nocfo.io) to your terminal and AI workflows — a single package powering a CLI client, an MCP server, and a Cursor AI skill.

## Features

- **All-in-one package** — CLI, MCP server, and Cursor skill from a single `pip install`
- **60+ MCP tools** across 11 domains (businesses, accounts, invoices, contacts, documents, and more)
- **OpenAPI-driven** — tools stay in sync with the live NoCFO API schema
- **PAT authentication** — simple token-based auth with config file, env var, or CLI flag
- **Dual output** — human-friendly tables for terminals, JSON for scripts and pipelines
- **Claude Desktop + Cursor** — works as stdio MCP server or standalone CLI
- **Zero-config run** — `uvx nocfo-cli --help` with no permanent install

## Quick Install

**pip** (recommended)

```bash
pip install nocfo-cli
```

**pipx** (isolated install)

```bash
pipx install nocfo-cli
```

**uvx** (no install needed)

```bash
uvx nocfo-cli --help
```

## Authentication

Create a Personal Access Token at [login.nocfo.io/auth/tokens](https://login.nocfo.io/auth/tokens), then configure once:

```bash
nocfo auth configure --token <your_pat>
nocfo auth status
```

Or pass via environment:

```bash
export NOCFO_API_TOKEN=<your_pat>
```

<details>
<summary>Auth precedence & defaults</summary>

| Priority | Source                            |
| -------- | --------------------------------- |
| 1        | `--api-token` CLI flag            |
| 2        | `NOCFO_API_TOKEN` env var         |
| 3        | `~/.config/nocfo-cli/config.json` |

Default base URL: `https://api-prd.nocfo.io`
Default output format: `table`

</details>

## Quick Start

```bash
nocfo user me                        # current user info
nocfo businesses list                # list all businesses
nocfo invoices list --business slug  # sales invoices
nocfo documents list --business slug --query date_from=2026-01-01
nocfo contacts create --business slug --field name=Acme
```

JSON output for automation:

```bash
nocfo --output json businesses list | jq '.results[]'
```

## Set Up with Claude Desktop (step-by-step)

Connect NoCFO to Claude so you can ask questions about your bookkeeping in plain language. No coding experience needed.

### 1. Install Python

NoCFO AI Toolkit needs Python 3.10 or newer.

**Mac** — open **Terminal** (search "Terminal" in Spotlight) and run:

```bash
brew install python
```

> Don't have Homebrew? Install it first: https://brew.sh

**Windows** — download from https://www.python.org/downloads/ and run the installer. **Check the box** "Add Python to PATH" during install.

Verify it works:

```bash
python3 --version
```

You should see `Python 3.10` or higher.

### 2. Get your NoCFO token

You need a Personal Access Token (PAT) so that Claude can read your NoCFO data on your behalf.

1. Open [login.nocfo.io/auth/tokens](https://login.nocfo.io/auth/tokens/) in your browser
2. **Log in** with your NoCFO account (Apple, Google, Microsoft, or email)
3. After login, you'll see the **API-avaimet** (API keys) page
4. Click **Luo uusi avain** ("Create new key")
5. Give the token a name you'll recognise, e.g. `Claude Desktop`
6. Click **Luo** ("Create")
7. The token appears once — **copy it now** and save it somewhere safe (e.g. a password manager). You won't be able to see it again.

> **Tip:** If you lose the token, you can always delete the old one and create a new one from the same page.

### 3. Configure Claude Desktop

1. Open **Claude Desktop**
2. Go to **Settings → Developer → Edit Config** (or open the file manually — see paths below)
3. Paste the following into the config file, replacing `your_token_here` with the token from step 2:

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

> If the file already has other servers configured, add the `"nocfo": { ... }` block inside the existing `"mcpServers"` object.

<details>
<summary>Config file locations</summary>

| OS      | Path                                                              |
| ------- | ----------------------------------------------------------------- |
| Mac     | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                     |

</details>

4. **Restart Claude Desktop**

### 4. Try it out

Open a new chat in Claude and ask:

- _"Listaa yritykseni"_
- _"Montako myyntilaskua on tällä kuussa?"_
- _"Ketkä ovat suurimmat asiakkaani?"_

Claude uses NoCFO tools automatically to answer. You'll see a tool icon when it accesses your data.

---

## Set Up with Cursor

Add the same config to Cursor's MCP settings (**Settings → MCP → Add Server**) using `nocfo mcp` as the stdio command and pass the token via the `NOCFO_API_TOKEN` env variable.

## MCP Server (advanced)

Start the MCP server manually from the terminal:

```bash
nocfo mcp
```

The server uses stdio transport. Any MCP-compatible client can connect to it.

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
