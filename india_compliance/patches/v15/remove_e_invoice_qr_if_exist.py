import frappe


def execute():
    if frappe.db.exists("Web Template", "e-Invoice QR"):
        frappe.db.delete("Web Template", "e-Invoice QR")
