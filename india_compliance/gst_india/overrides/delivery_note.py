import frappe

from india_compliance.gst_india.overrides.sales_invoice import (
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


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Delivery Note", data, "e-Waybill Log", "Integration Request"
    )
