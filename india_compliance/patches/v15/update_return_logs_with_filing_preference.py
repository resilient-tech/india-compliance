import frappe

from india_compliance.gst_india.utils.gstin_info import (
    fetch_filing_preference,
    get_filing_preference,
    get_fy,
)


def patch_filing_preference(gstin):
    logs = frappe.get_all(
        "GST Return Log",
        filters={
            "filing_preference": ["is", "not set"],
            "gstin": gstin,
            "return_period": ["!=", "ALL"],
            "return_type": ["in", ["GSTR1", "GSTR3B"]],
        },
        fields=["name", "return_period", "gstin"],
    )

    if not logs:
        return

    gst_return_log = {}
    for log in logs:
        response = fetch_filing_preference(gstin, get_fy(log.return_period))
        preference = get_filing_preference(log.return_period, response)
        gst_return_log[log.name] = {"filing_preference": preference}

    frappe.db.bulk_update("GST Return Log", gst_return_log, update_modified=False)
