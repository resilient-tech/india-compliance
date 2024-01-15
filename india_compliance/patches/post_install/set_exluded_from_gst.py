import frappe

from india_compliance.gst_india.constants import SALES_DOCTYPES
from frappe.query_builder.functions import IfNull

DOCTYPES = ["Sales Invoice", "Purchase Invoice"]


def execute():
    for doctype in DOCTYPES:
        party_gstin_field = (
            "billing_address_gstin" if doctype in SALES_DOCTYPES else "supplier_gstin"
        )

        doc = frappe.qb.DocType(doctype)

        (
            frappe.qb.update(doc)
            .set(doc.exclude_from_gst, 1)
            .where(
                (doc.is_opening == "Yes")
                | (IfNull(doc.company_gstin, "") == "")  # India registerd cmpany
                | (IfNull(doc.company_gstin, "") == doc[party_gstin_field])
            )
            .where(doc.docstatus != 0)
            .run()
        )
