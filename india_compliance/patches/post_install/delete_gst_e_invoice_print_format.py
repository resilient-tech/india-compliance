import frappe


def execute():
    frappe.delete_doc(
        "Print Format",
        "GST E-Invoice",
        force=True,
        ignore_permissions=True,
        ignore_missing=True,
    )
