import frappe


def execute():
    frappe.db.set_single_value(
        "GST Settings",
        {
            "enable_gstr_1_api": 1,
            "freeze_transactions": 1,
            "filing_frequency": "Monthly",
        },
    )
