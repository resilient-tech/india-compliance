import frappe
from frappe.desk.form.load import run_onload

from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import (
    auto_cancel_e_waybill,
    get_e_waybill_info,
)


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

    if e_waybill_info := get_e_waybill_info(doc):
        doc.set_onload("e_waybill_info", e_waybill_info)


def before_cancel(doc, method=None):
    run_onload(doc)
    gst_settings = frappe.get_cached_doc("GST Settings")

    if not is_api_enabled(gst_settings):
        return

    auto_cancel_e_waybill(doc, gst_settings=gst_settings)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Delivery Note", data, "e-Waybill Log", "Integration Request"
    )
