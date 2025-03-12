import frappe
from frappe.query_builder import Case


def execute():
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    boe_item = frappe.qb.DocType("Bill of Entry Item")

    frappe.qb.update(pi_item).set(
        pi_item.pending_boe_qty,
        Case().when(boe_item.name.isnotnull(), 0).else_(pi_item.qty),
    ).left_join(boe_item).on(boe_item.pi_detail == pi_item.name).run()
