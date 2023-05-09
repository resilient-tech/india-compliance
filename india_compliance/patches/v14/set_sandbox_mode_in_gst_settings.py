import frappe


def execute():
    if frappe.conf.ic_api_sandbox_mode:
        frappe.db.set_single_value("GST Settings", "sandbox_mode", 1)
