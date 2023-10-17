import frappe


def execute():
    custom_field = frappe.qb.DocType("Custom Field")
    (
        frappe.qb.update(custom_field)
        .set(custom_field.fetch_if_empty, 0)
        .where(custom_field.fieldname == "gst_hsn_code")
    ).run()
