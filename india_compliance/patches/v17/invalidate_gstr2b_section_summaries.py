import frappe


def execute():
    frappe.db.set_value(
        "GST Return Log",
        {"return_type": "GSTR2b", "section_summary": ("is", "set")},
        "section_summary",
        None,
        update_modified=False,
    )
