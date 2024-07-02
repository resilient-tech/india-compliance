import frappe

from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    set_taxes_and_totals,
    update_gst_details,
    validate_taxes_and_transaction,
)

FIELD_MAP = {
    "taxes": "taxes",
    "amount": "amount",
    "total_taxes": "total_taxes",
    "qty": "qty",
    "grand_total": "base_rounded_total",
    "company": "company",
    "total_taxable_value": "total_taxable_value",
}


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
    set_taxes_and_totals(doc, FIELD_MAP)


def validate(doc, method=None):
    validate_taxes_and_transaction(doc, FIELD_MAP)
