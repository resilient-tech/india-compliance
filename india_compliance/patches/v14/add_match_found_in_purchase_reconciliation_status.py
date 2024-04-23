import frappe


def execute():
    pi_and_boe_list = frappe.get_all(
        "GST Inward Supply",
        filters={"action": "No Action", "link_name": ("!=", "")},
        pluck="link_name",
    )
    if pi_and_boe_list:
        for doc in ("Purchase Invoice", "Bill of Entry"):
            frappe.db.set_value(
                doc,
                {"name": ("in", pi_and_boe_list)},
                "reconciliation_status",
                "Match Found",
            )
