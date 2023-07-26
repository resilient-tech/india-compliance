import frappe

from india_compliance.gst_india.overrides.sales_invoice import (
    get_e_waybill_info,
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

    e_waybill_info, e_waybill_company_gstin = get_e_waybill_info(doc)
    doc.set_onload(
        "e_waybill_info",
        e_waybill_info,
    )
    if e_waybill_company_gstin and e_waybill_company_gstin != doc.company_gstin:
        doc.set_onload(
            "e_waybill_generated_in_sandbox_mode",
            True,
        )


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Delivery Note", data, "e-Waybill Log", "Integration Request"
    )
