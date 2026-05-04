"""Curated MCP server instructions and compact docs."""

SERVER_INSTRUCTIONS = """You are connected to NoCFO, a bookkeeping and invoicing system.

Use `search_tools` to find the right tool, then execute it with `call_tool`.
Discover first, execute second: resolve exact resources before mutations.

Most tools take one top-level argument named `params`.
Call them as `{"params": {...}}`, for example
`common_current_business_retrieve` => `{"params": {"business": "current"}}`.
Tools with no arguments use `{}`.

Use `business="current"` unless the user explicitly selects another business.
Prefer user-facing identifiers: account numbers, document numbers, invoice
numbers, contact names, tag names, and tool handles returned by list tools.
For bookkeeping documents, `blueprint` is the editable posting plan and
`entries` are generated evidence to verify after create/update.
"""

BLUEPRINT_GUIDE = """# Blueprint Guide

Blueprint is the editable posting plan for a NoCFO accounting document.
When a document is created or updated, NoCFO recalculates realized journal
entries from the current blueprint.

Use account numbers when discussing bookkeeping with users. Fetch VAT codes and
rates with `constants_retrieve` using kind=vat_codes or kind=vat_rates
before creating or changing VAT-bearing blueprint rows.

Entries are read-only evidence of what the current blueprint produced. Use
`bookkeeping_entries_list` to explain or verify postings after create/update.
"""

GLOSSARY = """# NoCFO Glossary

- document: one bookkeeping record/business transaction, not an uploaded file.
- file: uploaded evidence such as a PDF or image.
- attachment: a file linked to a bookkeeping document.
- blueprint: editable posting plan used to generate entries.
- entry: realized journal line inside a document.
- account number: user-facing bookkeeping account number, e.g. 1910.
- resource ID: tool handle returned for resources that do not have a user-facing number.
- relation: link between two documents, similar to a Linear issue relation.
- tag: lightweight document label, similar to a Linear label.
- header: optional account grouping hierarchy, enabled only for some businesses.
"""
