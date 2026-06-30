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

Mutating tools accept one or more targets. When the user asks to change, delete,
or create several resources, make a single batched call with all targets (e.g.
pass every tool_handle/number/id in the plural field, or every new record in
`payloads`) instead of one call per resource. Each call needs exactly one
confirmation and returns a per-target `BatchResponse`; if `failed > 0`, inspect
`results[].error` and retry only the items whose `ok` is false. Batches are not
atomic — targets that already succeeded are not rolled back when others fail.

Different targets can get DIFFERENT changes in one confirmation. The `*_update`
tools take an `updates` list where each entry names one target and the fields to
change for it — so e.g. renaming account 1910 to X and 2000 to Y, or setting a
different due date on each of several invoices, is a single confirmed call, not one
per target. (`invoicing_*_update` and `bookkeeping_account_update`/`tag_update`/
`file_update` all follow this per-target shape.)

For bookkeeping DOCUMENTS use `bookkeeping_documents_bulk_edit`, which both replaces
content-derived values and gives different documents different edits in one call. It
has a per-target mode (`documents`: a list of groups, each with its own tool_handles
and edits — e.g. document A's account to 1090, documents B-D's to 1091, attach file 7
to document A) and a uniform mode (`edits` + a selector — e.g. "change account 1910
to 1031 on all documents"). Edits cover accounts, VAT codes/rates, tags, attachments,
contact, date, and description. Prefer it over `bookkeeping_document_update` (which
sets identical fields on a known handle set).

Files (receipts, invoices, statements) attach to documents as evidence. A file's
link to documents lives on the DOCUMENT, not on the file: `bookkeeping_file_update`
only edits a file's own metadata and never changes a document's attachments.
Attaching is per document — a receipt belongs to its own document — so attach with
`bookkeeping_documents_bulk_edit` in per-target mode: one group per document, each
with an add_attachments edit carrying that document's own file ids. Different
documents get different files in a single confirmation. (You can also pass
attachment_ids to `bookkeeping_document_create`/`bookkeeping_document_update` to set a
single document's attachments.) Before attaching, decide whether the file truly
belongs on the document: list likely-but-unattached files with
`bookkeeping_document_suggested_attachments_list` and inspect a file's recognized
content (merchant, type, total, dates) with `bookkeeping_file_retrieve`.
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
