import frappe

from india_compliance.gst_india.utils.gstin_info import fetch_filing_preference


def patch_filing_preference(gstin):
    logs = frappe.get_all(
        "GST Return Log",
        filters={
            "filing_preference": ["is", "not set"],
            "gstin": gstin,
            "return_period": ["!=", "ALL"],
        },
        fields=["name", "return_period", "gstin"],
    )

    if not logs:
        return

    gst_return_log = {}
    for log in logs:
        preference = fetch_filing_preference(log.gstin, log.return_period)
        gst_return_log[log.name] = {"filing_preference": preference}

    frappe.db.bulk_update("GST Return Log", gst_return_log, update_modified=False)
