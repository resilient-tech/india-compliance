import frappe


def execute():
    frappe.db.set_value(
        "Purchase Invoice",
        {"eligibility_for_itc": "Import Of Capital Goods"},
        "eligibility_for_itc",
        "Import Of Goods",
    )
