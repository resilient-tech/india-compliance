import frappe


def execute():
    for doctype in ("Customer", "Supplier", "Address"):
        if not frappe.db.has_column(doctype, "gst_category"):
            continue

        frappe.db.set_value(
            doctype, {"gst_category": "Consumer"}, "gst_category", "Unregistered"
        )
