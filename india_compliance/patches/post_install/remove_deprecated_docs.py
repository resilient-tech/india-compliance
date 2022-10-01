import frappe


def execute():
    to_delete = {
        "DocType": [
            "E Invoice Request Log",
            "E Invoice Settings",
            "E Invoice User",
            "HSN Tax Rate",
        ],
        "Print Format": [
            "GST E-Invoice",
        ],
        "Report": [
            "Eway Bill",
        ],
    }

    for doctype, names in to_delete.items():
        frappe.delete_doc(
            doctype,
            names,
            force=True,
            ignore_permissions=True,
            ignore_missing=True,
        )
