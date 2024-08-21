import frappe


def execute():
    docs = frappe.get_all(
        "GST Inward Supply",
        filters={"action": ["in", ["Accept My Values", "Accept Supplier Values"]]},
        pluck="name",
    )

    for doc in docs:
        frappe.db.set_value("GST Inward Supply", doc, "action", "Accept")
