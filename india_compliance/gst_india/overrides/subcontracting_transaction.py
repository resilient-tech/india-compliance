import frappe

from india_compliance.gst_india.constants.e_waybill import (
    SO_SR_FIELD_MAP,
    STOCK_ENTRY_FIELD_MAP,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    set_taxes_and_totals,
    update_gst_details,
    validate_taxes_and_transaction,
)


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not (
        is_api_enabled(gst_settings)
        and gst_settings.enable_e_waybill
        and gst_settings.enable_e_waybill_for_sc
    ):
        return

    doc.set_onload("e_waybill_info", get_e_waybill_info(doc))


def before_save(doc, method=None):
    update_gst_details(doc)


def before_submit(doc, method=None):
    update_gst_details(doc)


def before_validate(doc, method=None):
    field_map = (
        STOCK_ENTRY_FIELD_MAP if doc.doctype == "Stock Entry" else SO_SR_FIELD_MAP
    )
    set_taxes_and_totals(doc, field_map)


def validate(doc, method=None):
    field_map = (
        STOCK_ENTRY_FIELD_MAP if doc.doctype == "Stock Entry" else SO_SR_FIELD_MAP
    )
    validate_taxes_and_transaction(doc, field_map)
