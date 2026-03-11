import frappe
from frappe.query_builder.functions import DateFormat


def execute():
    """
    Set itc_claim_period based on posting_date for existing Purchase Invoice
    and Bill of Entry documents where itc_claim_period is not set.
    """
    update_itc_claim_period("Purchase Invoice")
    update_itc_claim_period("Bill of Entry")


def update_itc_claim_period(doctype):
    doc = frappe.qb.DocType(doctype)

    # Format: MMYYYY from posting_date
    posting_period = DateFormat(doc.posting_date, "%m%Y")

    (
        frappe.qb.update(doc)
        .set(doc.itc_claim_period, posting_period)
        .where(doc.itc_claim_period.isnull())
        .where(doc.docstatus == 1)
        .run()
    )
