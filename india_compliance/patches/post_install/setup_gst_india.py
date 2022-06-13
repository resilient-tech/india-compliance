import frappe


def execute():
    # delete custom field tax_id if it exists
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": "tax_id",
            "dt": ("in", ("Sales Order", "Sales Invoice", "Delivery Note")),
        },
    )
