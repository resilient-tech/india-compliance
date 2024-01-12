import frappe

from india_compliance.gst_india.constants import SALES_DOCTYPES

DOCTYPES = ["Sales Invoice", "Purchase Invoice", "Delivery Note", "Purchase Receipt"]


def execute():
    for doctype in DOCTYPES:
        party_gstin_field = (
            "billing_address_gstin" if doctype in SALES_DOCTYPES else "supplier_gstin"
        )

        doctype = frappe.qb.DocType(doctype)

        (
            frappe.qb.update(doctype)
            .set(doctype.exclude_from_gst, 1)
            .where(
                (doctype.is_opening == "Yes")
                | (doctype.company_gstin == doctype[party_gstin_field])
            )
            .run()
        )
