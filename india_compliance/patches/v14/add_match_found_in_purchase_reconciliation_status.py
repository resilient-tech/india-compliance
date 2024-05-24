import frappe

DOCTYPES = ("Purchase Invoice", "Bill of Entry")


def execute():
    for doctype in DOCTYPES:
        doc_names = frappe.get_all(
            "GST Inward Supply",
            filters={
                "action": "No Action",
                "link_name": ("!=", ""),
                "link_doctype": doctype,
            },
            pluck="link_name",
        )

        if not doc_names:
            continue

        frappe.db.set_value(
            doctype, {"name": ("in", doc_names)}, "reconciliation_status", "Match Found"
        )
