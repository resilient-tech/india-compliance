import frappe
from frappe.query_builder.functions import IfNull


def execute():
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")
    purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

    invoices_with_gst_rate = (
        frappe.qb.from_(purchase_invoice_item)
        .select(purchase_invoice_item.parent)
        .where(
            (
                IfNull(purchase_invoice_item.cgst_rate, 0)
                + IfNull(purchase_invoice_item.sgst_rate, 0)
                + IfNull(purchase_invoice_item.igst_rate, 0)
            )
            > 0
        )
        .distinct()
    )

    (
        frappe.qb.update(purchase_invoice)
        .set(purchase_invoice.is_boe_applicable, 1)
        .where(IfNull(purchase_invoice.itc_classification, "") == "Import Of Goods")
        .where(purchase_invoice.name.notin(invoices_with_gst_rate))
        .where(purchase_invoice.docstatus == 1)
    ).run()
