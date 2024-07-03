import frappe

from india_compliance.gst_india.overrides.transaction import validate_transaction
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    CustomTaxController,
    update_gst_details,
    validate_taxes,
)

STOCK_ENTRY_FIELD_MAP = {"total_taxable_value": "total_taxable_value"}
SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP = {"total_taxable_value": "total"}


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


def before_validate(doc, method=None):
    field_map = (
        STOCK_ENTRY_FIELD_MAP
        if doc.doctype == "Stock Entry"
        else SUBCONTRACTING_ORDER_RECEIPT_FIELD_MAP
    )
    CustomTaxController(doc, field_map).set_taxes_and_totals()


def validate(doc, method=None):
    validate_taxes(doc)
    validate_transaction(doc)
    update_gst_details(doc)
