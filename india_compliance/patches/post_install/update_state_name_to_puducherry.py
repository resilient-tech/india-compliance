import frappe


def execute():
    frappe.db.set_value(
        "Address",
        {"gst_state": "Pondicherry"},
        {
            "gst_state": "Puducherry",
            "state": "Puducherry",
        },
    )
