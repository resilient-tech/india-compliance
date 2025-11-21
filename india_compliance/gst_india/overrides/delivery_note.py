import frappe

from india_compliance.gst_india.overrides.sales_invoice import (
    is_e_waybill_applicable,
    is_shipping_address_in_india,
    update_dashboard_with_gst_logs,
    validate_port_address,
)
from india_compliance.gst_india.overrides.transaction import (
    validate_transaction,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        if doc.gst_category == "Overseas" and is_e_waybill_applicable(doc):

            doc.set_onload(
                "shipping_address_in_india", is_shipping_address_in_india(doc)
            )
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if (
        is_api_enabled(gst_settings)
        and gst_settings.enable_e_waybill
        and (
            gst_settings.enable_e_waybill_from_dn or gst_settings.auto_cancel_e_waybill
        )
        and (e_waybill_info := get_e_waybill_info(doc))
    ):
        doc.set_onload("e_waybill_info", e_waybill_info)


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    validate_port_address(doc)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Delivery Note", data, "e-Waybill Log", "Integration Request"
    )
