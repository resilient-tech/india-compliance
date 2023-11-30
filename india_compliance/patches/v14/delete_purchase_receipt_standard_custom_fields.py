import frappe

FIELDS = [
    "transporter_name",
    "lr_no",
    "lr_date",
]


def execute():
    frappe.db.delete(
        "Custom Field",
        filters={
            "dt": "Purchase Receipt",
            "fieldname": ("in", FIELDS),
        },
    )
