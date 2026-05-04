"""NoCFO-specific tool search helpers and BM25 transform extensions."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated, Any

from fastmcp.server.context import Context
from fastmcp.server.transforms.search import BM25SearchTransform
from fastmcp.tools.tool import Tool

# Seeded from nocfo-frontend localization terms (fi/en/sv/de) for core domains.
_SYNONYM_GROUPS: dict[str, set[str]] = {
    "performance": {
        "how is my business doing",
        "business doing",
        "business performance",
        "business health",
        "company performance",
        "financial performance",
        "kpi",
        "kpis",
        "dashboard",
        "runway",
        "burn",
        "profitability",
        "kannattavuus",
        "liiketoiminnan tilanne",
        "miten yrityksellä menee",
        "miten yritykselläni menee",
        "hur går det för företaget",
        "wie läuft mein unternehmen",
        "report",
        "reports",
        "financial report",
        "income statement",
        "balance sheet",
        "cash flow",
        "tuloslaskelma",
        "tase",
        "kassavirta",
        "raportti",
        "raportit",
        "resultaträkning",
        "balansräkning",
        "rapport",
        "rapporter",
        "gewinn und verlustrechnung",
        "bilanz",
        "bericht",
        "berichte",
    },
    "document": {
        "document",
        "documents",
        "bookkeeping document",
        "bookkeeping documents",
        "event",
        "events",
        "entry",
        "entries",
        "transaction",
        "transactions",
        "voucher",
        "vouchers",
        "tapahtuma",
        "tapahtumat",
        "kirjanpitotapahtuma",
        "kirjanpitotapahtumat",
        "tosite",
        "tositteet",
        "verifikat",
        "verifikation",
        "beleg",
        "belege",
        "dokument",
        "dokumente",
    },
    "account": {
        "account",
        "accounts",
        "chart of accounts",
        "ledger account",
        "tili",
        "tilit",
        "tilinumero",
        "tilikartta",
        "konto",
        "konton",
        "kontoplan",
        "kontonummer",
        "buchhaltungskonto",
        "konto nummer",
        "konten",
    },
    "invoice": {
        "invoice",
        "invoices",
        "sales invoice",
        "purchase invoice",
        "billing",
        "lasku",
        "laskut",
        "myyntilasku",
        "myyntilaskut",
        "ostolasku",
        "ostolaskut",
        "faktura",
        "fakturor",
        "försäljningsfaktura",
        "inköpsfaktura",
        "rechnung",
        "rechnungen",
        "verkaufsrechnung",
        "einkaufsrechnung",
    },
    "report": {
        "report",
        "reports",
        "financial report",
        "income statement",
        "balance sheet",
        "raportti",
        "raportit",
        "tuloslaskelma",
        "tase",
        "rapport",
        "rapporter",
        "resultaträkning",
        "balansräkning",
        "bericht",
        "berichte",
        "gewinn und verlustrechnung",
        "bilanz",
    },
    "vat": {
        "vat",
        "value added tax",
        "alv",
        "arvonlisävero",
        "moms",
        "mwst",
        "umsatzsteuer",
    },
    "period": {
        "period",
        "periods",
        "accounting period",
        "fiscal period",
        "vat period",
        "kausi",
        "kaudet",
        "tilikausi",
        "tilikaudet",
        "bokföringsperiod",
        "perioder",
        "redovisningsperiod",
        "zeitraum",
        "zeiträume",
        "abrechnungszeitraum",
        "buchungszeitraum",
    },
    "contact": {
        "contact",
        "contacts",
        "customer",
        "supplier",
        "yhteystieto",
        "yhteystiedot",
        "asiakas",
        "toimittaja",
        "kontakt",
        "kontakter",
        "kunde",
        "leverantör",
        "kontakt",
        "kontakte",
        "kunde",
        "lieferant",
    },
    "product": {
        "product",
        "products",
        "item",
        "items",
        "tuote",
        "tuotteet",
        "produkt",
        "produkter",
        "produkt",
        "produkte",
    },
    "tag": {
        "tag",
        "tags",
        "label",
        "labels",
        "tunniste",
        "tunnisteet",
        "tagg",
        "taggar",
        "etikett",
        "etiketter",
    },
    "file": {
        "file",
        "files",
        "attachment",
        "attachments",
        "tiedosto",
        "tiedostot",
        "liite",
        "liitteet",
        "fil",
        "filer",
        "bilaga",
        "datei",
        "dateien",
        "anhang",
    },
}

_INTENT_TOOL_PREFIXES: dict[str, tuple[str, ...]] = {
    "performance": (
        "reporting_balance_sheet_",
        "reporting_equity_changes_",
        "reporting_income_statement_",
        "reporting_journal_",
        "reporting_ledger_",
        "reporting_vat_",
        "reporting_accounting_periods_",
        "reporting_accounting_period_",
        "reporting_vat_periods_",
        "reporting_vat_period_",
    ),
    "contact": ("invoicing_contacts_", "invoicing_contact_"),
    "invoice": (
        "invoicing_sales_invoices_",
        "invoicing_sales_invoice_",
        "invoicing_purchase_invoices_",
        "invoicing_purchase_invoice_",
    ),
    "document": (
        "bookkeeping_documents_",
        "bookkeeping_document_",
        "bookkeeping_entries_",
        "bookkeeping_document_relations_",
        "bookkeeping_document_relation_",
    ),
    "account": ("bookkeeping_accounts_", "bookkeeping_account_"),
    "report": (
        "reporting_balance_sheet_",
        "reporting_equity_changes_",
        "reporting_income_statement_",
        "reporting_journal_",
        "reporting_ledger_",
        "reporting_vat_",
        "reporting_accounting_periods_",
        "reporting_accounting_period_",
        "reporting_vat_periods_",
        "reporting_vat_period_",
    ),
    "period": (
        "reporting_accounting_periods_",
        "reporting_accounting_period_",
        "reporting_vat_periods_",
        "reporting_vat_period_",
    ),
    "vat": ("reporting_vat_periods_", "reporting_vat_period_"),
    "product": ("invoicing_products_", "invoicing_product_"),
    "tag": ("bookkeeping_tags_", "bookkeeping_tag_"),
    "file": ("bookkeeping_files_", "bookkeeping_file_"),
}


def _contains_term(text: str, term: str) -> bool:
    if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None:
        return True
    # Support common inflected forms (e.g. tapahtumaa, verifikationen).
    return len(term) >= 5 and term in text


def expand_query_with_synonyms(query: str) -> str:
    """Expand a natural-language query with domain synonyms."""
    lowered = query.strip().lower()
    if not lowered:
        return query

    expansions: set[str] = set()
    for terms in _SYNONYM_GROUPS.values():
        if any(_contains_term(lowered, term) for term in terms):
            expansions.update(terms)

    if not expansions:
        return query

    return f"{query} {' '.join(sorted(expansions))}"


def _detect_intent_domains(query: str) -> set[str]:
    lowered = query.strip().lower()
    if not lowered:
        return set()
    matches: set[str] = set()
    for domain, terms in _SYNONYM_GROUPS.items():
        if any(_contains_term(lowered, term) for term in terms):
            matches.add(domain)
    # "customer" workflows typically map to contact tools.
    if "customer" in matches:
        matches.add("contact")
    return matches


def _intent_ranked_tools(
    tools: Sequence[Tool],
    detected_domains: set[str],
) -> list[Tool]:
    prefixes: list[str] = []
    for domain in sorted(detected_domains):
        prefixes.extend(_INTENT_TOOL_PREFIXES.get(domain, ()))
    if not prefixes:
        return []
    ranked: list[Tool] = []
    seen_names: set[str] = set()
    for tool in tools:
        for prefix in prefixes:
            if tool.name.startswith(prefix):
                ranked.append(tool)
                seen_names.add(tool.name)
                break
        else:
            if (
                {"performance", "report"} & detected_domains
                and "report" in tool.name
                and tool.name not in seen_names
            ):
                ranked.append(tool)
                seen_names.add(tool.name)
    return ranked


class NocfoBM25SearchTransform(BM25SearchTransform):
    """BM25 search transform with multilingual NoCFO synonym expansion."""

    def _make_call_tool(self) -> Tool:
        """Create a tolerant call_tool proxy accepting arguments or parameters."""
        transform = self

        async def call_tool(
            name: Annotated[str, "The name of the tool to call"],
            arguments: Annotated[
                dict[str, Any] | None, "Arguments to pass to the tool"
            ] = None,
            parameters: Annotated[
                dict[str, Any] | None,
                "Alias for arguments used by some LLM tool-call formats",
            ] = None,
            ctx: Context = None,  # type: ignore[assignment]  # ty:ignore[invalid-parameter-default]
        ) -> Any:
            if name in {transform._call_tool_name, transform._search_tool_name}:
                raise ValueError(
                    f"'{name}' is a synthetic search tool and cannot be called via the call_tool proxy"
                )
            resolved_arguments = arguments if arguments is not None else parameters
            return await ctx.fastmcp.call_tool(name, resolved_arguments)

        return Tool.from_function(fn=call_tool, name=self._call_tool_name)

    async def _search(self, tools: Sequence[Tool], query: str) -> Sequence[Tool]:
        expanded_query = expand_query_with_synonyms(query)
        bm25_ranked = list(await super()._search(tools, expanded_query))
        detected_domains = _detect_intent_domains(expanded_query)
        intent_ranked = _intent_ranked_tools(tools, detected_domains)
        merged: list[Tool] = []
        seen_names: set[str] = set()
        for tool in [*intent_ranked, *bm25_ranked]:
            if tool.name in seen_names:
                continue
            merged.append(tool)
            seen_names.add(tool.name)
        limit = max(len(bm25_ranked), 1)
        return merged[:limit]
