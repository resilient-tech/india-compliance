import frappe


def execute():
    purchase_invoices = frappe.get_all(
        "GST Inward Supply",
        filters={"action": "No Action", "link_name": ["!=", ""]},
        pluck="link_name",
    )
    frappe.db.set_value(
        "Purchase Invoice",
        {"name": ("in", purchase_invoices)},
        "reconciliation_status",
        "Match Found",
    )
