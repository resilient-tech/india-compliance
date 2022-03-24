import frappe


def execute():
    # delete_custom_field_tax_id_if_exists
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": "tax_id",
            "dt": ("in", ("Sales Order", "Sales Invoice", "Delivery Note")),
        },
    )
