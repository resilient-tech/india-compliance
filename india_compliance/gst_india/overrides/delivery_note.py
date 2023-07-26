import frappe

from india_compliance.gst_india.overrides.sales_invoice import (
    get_ewaybill_party_gstin_from_log,
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.utils import is_api_enabled


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not (
        is_api_enabled(gst_settings)
        and gst_settings.enable_e_waybill
        and gst_settings.enable_e_waybill_from_dn
    ):
        return

    doc.set_onload(
        "e_waybill_info",
        frappe.get_value(
            "e-Waybill Log",
            doc.ewaybill,
            ("created_on", "valid_upto"),
            as_dict=True,
        ),
    )

    eway_bill_party_gstin = get_ewaybill_party_gstin_from_log(doc)
    if eway_bill_party_gstin != doc.company_gstin:
        doc.set_onload(
            "set_ewaybill_description",
            True,
        )


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Delivery Note", data, "e-Waybill Log", "Integration Request"
    )
