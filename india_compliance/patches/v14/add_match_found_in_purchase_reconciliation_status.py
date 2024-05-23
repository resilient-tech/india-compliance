import frappe

DOCTYPES = ("Purchase Invoice", "Bill of Entry")


def execute():
    for doctype in DOCTYPES:
        docs = get_inward_supply(doctype)
        if not docs:
            continue
        frappe.db.set_value(
            doctype,
            {"name": ("in", docs)},
            "reconciliation_status",
            "Match Found",
        )


def get_inward_supply(doctype):
    return frappe.get_all(
        "GST Inward Supply",
        filters={
            "action": "No Action",
            "link_name": ("!=", ""),
            "link_doctype": doctype,
        },
        pluck="link_name",
    )
