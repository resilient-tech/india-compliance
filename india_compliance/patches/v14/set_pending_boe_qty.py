import frappe
from frappe.query_builder import Case


def execute():
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    boe_item = frappe.qb.DocType("Bill of Entry Item")

    frappe.qb.update(pi_item).left_join(boe_item).on(
        boe_item.pi_detail == pi_item.name
    ).set(
        pi_item.pending_boe_qty,
        Case()
        .when(((boe_item.name.isnotnull()) & (boe_item.docstatus == 1)), 0)
        .else_(pi_item.qty),
    ).run(
        debug=True
    )
