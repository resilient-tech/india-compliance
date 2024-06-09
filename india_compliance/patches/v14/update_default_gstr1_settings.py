import frappe


def execute():
    frappe.db.set_single_value(
        "GST Settings",
        {
            "compare_gstr_1_data": 1,
            "freeze_transactions": 1,
            "filing_frequency": "Monthly",
        },
    )
