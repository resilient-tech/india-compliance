import frappe


def execute():
    for doctype in ("Customer", "Supplier", "Address"):
        if frappe.db.has_column(doctype, "gst_category"):
            frappe.db.set_value(
                doctype, {"gst_category": "Consumer"}, "gst_category", "Unregistered"
            )
