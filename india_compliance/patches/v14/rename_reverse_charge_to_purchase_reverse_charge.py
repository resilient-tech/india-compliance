import frappe


def execute():
    frappe.db.set_value(
        "GST Account",
        {"account_type": "Reverse Charge"},
        "account_type",
        "Purchase Reverse Charge",
    )
