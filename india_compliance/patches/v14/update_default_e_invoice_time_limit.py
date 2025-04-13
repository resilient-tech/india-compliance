import frappe


def execute():
    frappe.db.set_single_value(
        "GST Settings", {"e_invoice_reporting_time_limit_days": 30}
    )
