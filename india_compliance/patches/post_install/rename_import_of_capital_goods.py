import frappe


def execute():
    if "eligibility_for_itc" not in frappe.db.get_table_columns("Purchase Invoice"):
        return

    frappe.db.set_value(
        "Purchase Invoice",
        {"eligibility_for_itc": "Import Of Capital Goods"},
        "eligibility_for_itc",
        "Import Of Goods",
    )
