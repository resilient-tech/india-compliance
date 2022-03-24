import frappe


def execute():
    for doctype in ("Customer", "Supplier", "Address"):
        frappe.db.set_value(
            doctype, {"gst_category": "Consumer"}, "gst_category", "Unregistered"
        )
