import frappe


def execute():
    if frappe.db.get_single_value("GST Settings", "gstin_status_refresh_interval") < 15:
        frappe.db.set_single_value("GST Settings", "gstin_status_refresh_interval", 15)
