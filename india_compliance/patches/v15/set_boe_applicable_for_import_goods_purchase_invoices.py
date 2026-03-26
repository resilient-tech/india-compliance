import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.constants import TAX_TYPES


def execute():
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")
    purchase_invoice_tax = frappe.qb.DocType("Purchase Taxes and Charges")

    invoices_with_gst_taxes = (
        frappe.qb.from_(purchase_invoice_tax)
        .select(purchase_invoice_tax.parent)
        .where(purchase_invoice_tax.parenttype == "Purchase Invoice")
        .where(purchase_invoice_tax.gst_tax_type.isin(TAX_TYPES))
        .distinct()
    )

    (
        frappe.qb.update(purchase_invoice)
        .set(purchase_invoice.is_boe_applicable, 1)
        .where(IfNull(purchase_invoice.itc_classification, "") == "Import Of Goods")
        .where(purchase_invoice.name.notin(invoices_with_gst_taxes))
        .where(purchase_invoice.docstatus == 1)
    ).run()
