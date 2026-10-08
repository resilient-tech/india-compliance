import frappe
from frappe.query_builder.functions import IfNull, Sum


def execute():
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    boe_item = frappe.qb.DocType("Bill of Entry Item")

    submitted_boe_qty = (
        frappe.qb.from_(boe_item)
        .select(Sum(boe_item.qty))
        .where(boe_item.pi_detail == pi_item.name)
        .where(boe_item.docstatus == 1)
    )

    overseas_invoices = (
        frappe.qb.from_(pi).select(pi.name).where(pi.docstatus == 1).where(pi.gst_category == "Overseas")
    )

    (
        frappe.qb.update(pi_item)
        .set(
            pi_item.pending_boe_qty,
            pi_item.qty - IfNull(submitted_boe_qty, 0),
        )
        .where(pi_item.parent.isin(overseas_invoices))
        .run()
    )
