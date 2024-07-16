import frappe


def execute():
    settings = frappe.get_single("GST Settings")

    frappe.db.set_value(
        "Scheduled Job Type",
        {
            "method": "india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool.auto_refresh_authtoken"
        },
        "stopped",
        not settings.enable_auto_reconciliation,
    )
