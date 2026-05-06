from __future__ import annotations

from types import SimpleNamespace

from nocfo_toolkit.mcp.search import _detect_intent_domains, _intent_ranked_tools


def test_document_intent_prefers_bookkeeping_documents_list_tool() -> None:
    domains = _detect_intent_domains("montako tapahtumaa kirjanpidossa")
    tools = [
        SimpleNamespace(name="invoicing_sales_invoices_list"),
        SimpleNamespace(name="bookkeeping_documents_list"),
        SimpleNamespace(name="bookkeeping_entries_list"),
    ]

    ranked = _intent_ranked_tools(tools, domains)
    names = [tool.name for tool in ranked]

    assert "bookkeeping_documents_list" in names


def test_other_domain_intents_match_plural_list_tools() -> None:
    tools = [
        SimpleNamespace(name="bookkeeping_accounts_list"),
        SimpleNamespace(name="invoicing_contacts_list"),
        SimpleNamespace(name="invoicing_sales_invoices_list"),
        SimpleNamespace(name="invoicing_purchase_invoices_list"),
        SimpleNamespace(name="reporting_accounting_periods_list"),
        SimpleNamespace(name="reporting_vat_periods_list"),
    ]

    account_names = [
        tool.name
        for tool in _intent_ranked_tools(
            tools, _detect_intent_domains("montako tili kirjanpidossa")
        )
    ]
    assert "bookkeeping_accounts_list" in account_names

    contact_names = [
        tool.name
        for tool in _intent_ranked_tools(
            tools, _detect_intent_domains("montako asiakasta")
        )
    ]
    assert "invoicing_contacts_list" in contact_names

    invoice_names = [
        tool.name
        for tool in _intent_ranked_tools(
            tools, _detect_intent_domains("montako laskua")
        )
    ]
    assert "invoicing_sales_invoices_list" in invoice_names

    period_names = [
        tool.name
        for tool in _intent_ranked_tools(
            tools, _detect_intent_domains("montako alv-kautta")
        )
    ]
    assert "reporting_vat_periods_list" in period_names
