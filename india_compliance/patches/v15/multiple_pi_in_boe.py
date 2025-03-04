import frappe


def execute():
    boe = frappe.qb.DocType("Bill of Entry", alias="boe")
    boe_item = frappe.qb.DocType("Bill of Entry Item", alias="boe_item")

    # link BOE Item to it's purchase invoice
    (
        frappe.qb.update(boe_item)
        .join(boe)
        .on(boe_item.parent == boe.name)
        .set(boe_item.purchase_invoice, boe.purchase_invoice)
        .run(as_dict=True)
    )
