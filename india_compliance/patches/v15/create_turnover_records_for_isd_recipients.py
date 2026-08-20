import frappe

from india_compliance.gst_india.constants import ISD_GST_CATEGORY
from india_compliance.gst_india.doctype.turnover_record.turnover_record import (
    get_relevant_period,
    get_turnover_from_sales_invoices,
    upsert_turnover_record,
)


def execute():
    """Backfill Turnover Records for the recipients of every ISD registered company"""

    isd_pans = {}
    for address in get_company_addresses(isd=True).run(as_dict=True):
        if address.gstin:
            isd_pans.setdefault(address.company, set()).add(address.gstin[2:12])

    if not isd_pans:
        return

    from_date, to_date = get_relevant_period()

    for company, pans in isd_pans.items():
        for gstin, amount in get_turnover_by_gstin(company, pans, from_date, to_date).items():
            upsert_turnover_record(company=company, gstin=gstin, gst_state=None, amount=amount)


def get_turnover_by_gstin(company, isd_pans, from_date, to_date):
    """Credit only ever reaches the ISD's own legal entity, so skip unregistered company addresses
    -- job worker sites and the like -- along with any registration on a different PAN."""
    turnover = {}

    for gstin in {address.gstin for address in get_recipient_addresses([company])}:
        if not gstin or gstin[2:12] not in isd_pans:
            continue

        amount = get_turnover_from_sales_invoices(gstin, from_date, to_date, company)
        if amount:
            turnover[gstin] = amount

    return turnover


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


def get_recipient_addresses(companies):
    """Non ISD company addresses — the branches credit is distributed to."""
    dynamic_link = frappe.qb.DocType("Dynamic Link")

    return (
        get_company_addresses(isd=False).where(dynamic_link.link_name.isin(list(companies))).run(as_dict=True)
    )
