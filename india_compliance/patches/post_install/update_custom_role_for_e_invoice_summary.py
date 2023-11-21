import frappe


def execute():
    frappe.db.set_value(
        "Custom Role", {"report": "E-Invoice Summary"}, "report", "e-Invoice Summary"
    )
