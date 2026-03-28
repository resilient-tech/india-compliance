import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.constants import TAX_TYPES


def execute():
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_tax = frappe.qb.DocType("Purchase Taxes and Charges")

    invoices_with_gst_taxes = (
        frappe.qb.from_(pi_tax)
        .select(pi_tax.parent)
        .where(pi_tax.parenttype == "Purchase Invoice")
        .where(pi_tax.gst_tax_type.isin(TAX_TYPES))
        .distinct()
    )

    (
        frappe.qb.update(pi)
        .set(pi.is_boe_applicable, 1)
        .where(IfNull(pi.itc_classification, "") == "Import Of Goods")
        .where(pi.name.notin(invoices_with_gst_taxes))
        .where(pi.docstatus == 1)
    ).run()
