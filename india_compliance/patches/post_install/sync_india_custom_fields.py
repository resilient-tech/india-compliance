import frappe


def execute():
    for doctype in ("Sales Invoice", "Delivery Note", "Purchase Invoice"):
        frappe.db.sql(
            """DELETE FROM `tabCustom Field`
                WHERE dt = %s
                AND fieldname IN ('port_code', 'shipping_bill_number', 'shipping_bill_date')""",
            doctype,
        )

    frappe.db.sql(
        """UPDATE tabAddress SET gst_state_number=concat("0", gst_state_number)
            WHERE length(gst_state_number) = 1;"""
    )
