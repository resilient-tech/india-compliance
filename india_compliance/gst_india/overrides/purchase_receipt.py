import frappe
from frappe.desk.form.load import run_onload

from india_compliance.gst_india.overrides.purchase_invoice import (
    set_ineligibility_reason,
)
from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import (
    ignore_gst_validations,
    validate_mandatory_fields,
    validate_transaction,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import (
    auto_cancel_e_waybill,
    get_e_waybill_info,
)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Purchase Receipt",
        data,
        "e-Waybill Log",
        "Integration Request",
    )


def onload(doc, method=None):
    if ignore_gst_validations(doc):
        return

    if (
        validate_mandatory_fields(
            doc, ("company_gstin", "place_of_supply", "gst_category"), throw=False
        )
        is False
    ):
        return

    set_ineligibility_reason(doc, show_alert=False)

    # Load e-waybill info if applicable
    if doc.get("ewaybill"):
        gst_settings = frappe.get_cached_doc("GST Settings")
        if (
            is_api_enabled(gst_settings)
            and gst_settings.enable_e_waybill
            and gst_settings.enable_e_waybill_from_pr
            and (e_waybill_info := get_e_waybill_info(doc))
        ):
            doc.set_onload("e_waybill_info", e_waybill_info)


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    set_ineligibility_reason(doc)


def before_cancel(doc, method=None):
    run_onload(doc)
    gst_settings = frappe.get_cached_doc("GST Settings")

    if not is_api_enabled(gst_settings):
        return

    auto_cancel_e_waybill(doc, gst_settings=gst_settings)
