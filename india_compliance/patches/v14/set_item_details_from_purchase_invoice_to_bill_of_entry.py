import frappe
from frappe.query_builder import Bracket


def execute():
    boe_item = frappe.qb.DocType("Bill of Entry Item")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    def from_purchase_invoice_item(column):
        return Bracket(frappe.qb.from_(pi_item).select(column).where(pi_item.name == boe_item.pi_detail))

    (
        frappe.qb.update(boe_item)
        .set(boe_item.gst_hsn_code, from_purchase_invoice_item(pi_item.gst_hsn_code))
        .set(boe_item.qty, from_purchase_invoice_item(pi_item.qty))
        .set(boe_item.uom, from_purchase_invoice_item(pi_item.uom))
        .where(boe_item.docstatus == 1)
        .run()
    )
