import frappe


def execute():
    settings = frappe.get_single("GST Settings")

    settings.db_set(
        "generate_e_waybill_with_e_invoice",
        (
            0
            if (
                settings.auto_generate_e_invoice
                and not settings.auto_generate_e_waybill
            )
            else 1
        ),
    )
