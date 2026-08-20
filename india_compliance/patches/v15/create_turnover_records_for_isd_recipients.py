import frappe

from india_compliance.gst_india.constants import ISD_GST_CATEGORY
from india_compliance.gst_india.doctype.turnover_record.turnover_record import (
    get_relevant_period,
    get_turnover_from_sales_invoices,
    upsert_turnover_record,
)


def execute():
    """Backfill Turnover Records for the recipients of every ISD registered company"""

    companies = get_companies_with_isd_registration()
    if not companies:
        return

    from_date, to_date = get_relevant_period()

    # Turnover Record holds one amount per state per period, so aggregate every GSTIN of a state
    turnover_by_state = {}
    for address in get_recipient_addresses(companies):
        amount = get_turnover_from_sales_invoices(address.gstin, from_date, to_date, address.company)
        if not amount:
            continue

        state = turnover_by_state.setdefault(address.gst_state, frappe._dict(gstin=address.gstin, amount=0))
        state.amount += amount

    for gst_state, turnover in turnover_by_state.items():
        upsert_turnover_record(
            gstin=turnover.gstin,
            gst_state=gst_state,
            amount=turnover.amount,
            period=(from_date, to_date),
        )


def get_company_addresses(isd):
    """Company owned addresses, with the ISD / non ISD gst_category as required."""
    address = frappe.qb.DocType("Address")
    dynamic_link = frappe.qb.DocType("Dynamic Link")

    category_condition = (
        address.gst_category == ISD_GST_CATEGORY if isd else address.gst_category != ISD_GST_CATEGORY
    )

    return (
        frappe.qb.from_(address)
        .join(dynamic_link)
        .on((dynamic_link.parent == address.name) & (dynamic_link.parenttype == "Address"))
        .select(
            dynamic_link.link_name.as_("company"),
            address.gstin,
            address.gst_state,
        )
        .where((dynamic_link.link_doctype == "Company") & category_condition)
        .distinct()
    )


def get_companies_with_isd_registration():
    return {row.company for row in get_company_addresses(isd=True).run(as_dict=True)}


def get_recipient_addresses(companies):
    """Non ISD company addresses — the branches credit is distributed to."""
    dynamic_link = frappe.qb.DocType("Dynamic Link")

    return (
        get_company_addresses(isd=False).where(dynamic_link.link_name.isin(list(companies))).run(as_dict=True)
    )
