import frappe


def execute():
    frappe.db.set_value("GST Credential", {"service": "Returns"}, "auth_token", None)
