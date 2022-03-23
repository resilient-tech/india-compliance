import frappe


def execute():
    fields = ("port_code", "shipping_bill_number", "shipping_bill_date")
    frappe.db.delete(
        "Custom Field", {"dt": "Purchase Invoice", "fieldname": ("in", fields)}
    )

    frappe.db.sql(
        """UPDATE tabAddress SET gst_state_number=concat("0", gst_state_number)
            WHERE length(gst_state_number) = 1"""
    )
