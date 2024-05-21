import frappe


def execute():
    gst_settings = frappe.get_cached_doc("GST Settings")

    if frappe.db.exists("Sales Invoice", {"ecommerce_gstin": ["!=", ""]}):
        gst_settings.enable_sales_through_ecommerce_operators = 1
        gst_settings.save()
        return
