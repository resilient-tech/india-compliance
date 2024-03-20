import frappe


def execute():
    boe_item = frappe.qb.DocType("Bill of Entry Item", alias="boe_item")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    (
        frappe.qb.update(boe_item)
        .left_join(pi_item)
        .on(pi_item.name == boe_item.pi_detail)
        .set(boe_item.gst_hsn_code, pi_item.gst_hsn_code)
        .set(boe_item.qty, pi_item.qty)
        .set(boe_item.uom, pi_item.uom)
        .where(boe_item.docstatus == 1)
        .run()
    )
