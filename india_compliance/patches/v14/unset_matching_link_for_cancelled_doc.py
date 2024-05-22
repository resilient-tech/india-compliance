import frappe


def execute():
    import_logs = frappe.get_all(
        "GST Inward Supply",
        filters={
            "link_doctype": ("in", ("Purchase Invoice", "Bill of Entry")),
        },
        fields=["link_name", "link_doctype", "name"],
    )

    for log in import_logs:
        doc_status = frappe.db.get_value(
            log.get("link_doctype"), log.get("link_name"), "docstatus"
        )
        if doc_status != 2:
            continue

        frappe.db.set_value(
            "GST Inward Supply",
            log.get("name"),
            {"link_name": "", "link_doctype": "", "match_status": ""},
        )
