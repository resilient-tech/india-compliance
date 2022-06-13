import frappe


def execute():
    delete_tax_id_custom_field()
    set_correct_state_number()
    remove_shipping_fields_from_purchase_invoice()


def delete_tax_id_custom_field():
    # delete custom field tax_id if it exists
    # this field was move to core ERPNext
    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": "tax_id",
            "dt": ("in", ("Sales Order", "Sales Invoice", "Delivery Note")),
        },
    )


def set_correct_state_number():
    # set correct state number for all states with single digit state number
    frappe.db.sql(
        """UPDATE tabAddress SET gst_state_number=concat("0", gst_state_number)
            WHERE length(gst_state_number) = 1"""
    )


def remove_shipping_fields_from_purchase_invoice():
    frappe.db.delete(
        "Custom Field",
        {
            "dt": "Purchase Invoice",
            "fieldname": (
                "in",
                ("port_code", "shipping_bill_number", "shipping_bill_date"),
            ),
        },
    )
