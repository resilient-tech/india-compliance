import frappe


def execute():
    frappe.delete_doc(
        "Print Format",
        "GST E-Invoice",
        ignore_missing=True,
        force=True,
        ignore_permissions=True,
    )
