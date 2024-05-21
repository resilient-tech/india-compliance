import frappe


def execute():
    gst_settings = frappe.get_cached_doc("GST Settings")
    for doctype in ["Sales Invoice", "Sales Order", "Delivery Note"]:
        if frappe.db.exists(doctype, {"ecommerce_gstin": ["!=", ""]}):
            gst_settings.enable_sales_through_ecommerce_operators = 1
            gst_settings.save()
            return
