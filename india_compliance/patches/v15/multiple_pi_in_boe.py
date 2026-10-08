import frappe
from frappe.query_builder import Bracket


def execute():
    boe = frappe.qb.DocType("Bill of Entry", alias="boe")
    boe_item = frappe.qb.DocType("Bill of Entry Item")

    # link BOE Item to it's purchase invoice
    parent_purchase_invoice = (
        frappe.qb.from_(boe).select(boe.purchase_invoice).where(boe.name == boe_item.parent)
    )

    (
        frappe.qb.update(boe_item)
        .set(boe_item.purchase_invoice, Bracket(parent_purchase_invoice))
        .where(boe_item.parent.isin(frappe.qb.from_(boe).select(boe.name)))
        .run()
    )
