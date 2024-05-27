import frappe


def execute():
    frappe.db.delete(
        "GSTR Import Log",
        filters={
            "data_not_found": 1,
            "return_type": "GSTR2b",
        },
    )
