import frappe

from india_compliance.gst_india.utils.custom_fields import delete_old_fields


def execute():
    invoice_type_gst_category_map = {
        "Regular": "Registered Regular",
        "Export": "Overseas",
        "SEZ": "SEZ",
        "Deemed Export": "Deemed Export",
    }

    doctypes = ("Sales Invoice", "Purchase Invoice")
    for doctype in doctypes:
        if not frappe.db.exists(
            "Custom Field", {"dt": doctype, "fieldname": "invoice_type"}
        ):
            continue

        for invoice_type, gst_category in invoice_type_gst_category_map.items():
            frappe.db.set_value(
                doctype,
                {"gst_category": ("in", (None, "")), "invoice_type": invoice_type},
                "gst_category",
                gst_category,
            )

    delete_old_fields("invoice_type", doctypes)

    if "eligibility_for_itc" not in frappe.db.get_table_columns("Purchase Invoice"):
        return

    # update eligibility_for_itc with new options
    for old_value, new_value in {
        "ineligible": "Ineligible",
        "input service": "Input Service Distributor",
        "capital goods": "Import Of Goods",
        "input": "All Other ITC",
    }.items():
        frappe.db.set_value(
            "Purchase Invoice",
            {"eligibility_for_itc": old_value},
            "eligibility_for_itc",
            new_value,
        )
