import frappe


def execute():
    # Discard the action "Accept Supplier Values"
    frappe.db.set_value(
        "GST Inward Supply",
        {"action": ["in", ["Accept My Values", "Accept Supplier Values"]]},
        "action",
        "Accept",
    )
