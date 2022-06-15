import frappe


def execute():
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": "customer_gstin",
            "dt": (
                "in",
                (
                    "Sales Invoice",
                    "Delivery Note",
                    "POS Invoice",
                    "Sales Order",
                ),
            ),
        },
    )
