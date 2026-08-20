import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.constants import ISD_GST_CATEGORY


def execute():
    """
    Backfill is_isd_applicable on submitted Purchase Invoices.
    """
    pi = frappe.qb.DocType("Purchase Invoice")
    address = frappe.qb.DocType("Address")

    isd_addresses = (
        frappe.qb.from_(address).select(address.name).where(address.gst_category == ISD_GST_CATEGORY)
    )

    (
        frappe.qb.update(pi)
        .set(pi.is_isd_applicable, 1)
        .where(pi.docstatus == 1)
        .where(pi.billing_address.isin(isd_addresses))
        .where(IfNull(pi.ineligibility_reason, "") != "ITC restricted due to PoS rules")
        .where(IfNull(pi.is_opening, "") != "Yes")
        .where(pi.is_reverse_charge == 0)
        .where(pi.is_return == 0)
    ).run()
