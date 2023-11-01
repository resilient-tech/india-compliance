import frappe

from india_compliance.gst_india.setup import EMAIL_TEMPLATE_DATA


def execute():
    doctype = EMAIL_TEMPLATE_DATA.pop("doctype")
    name = EMAIL_TEMPLATE_DATA.pop("name")

    if not frappe.db.exists(doctype, name):
        return

    frappe.db.set_value(doctype, name, EMAIL_TEMPLATE_DATA)
