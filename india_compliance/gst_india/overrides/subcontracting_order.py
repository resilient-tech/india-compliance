import frappe

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    update_gst_details,
)
from india_compliance.gst_india.overrides.ineligible_itc import update_valuation_rate
from india_compliance.gst_india.overrides.stock_entry import (
    set_item_wise_tax_rates,
    set_taxable_value,
    set_total_taxes,
    validate_taxes,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info


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


def validate(doc, method=None):
    # This has to be called after `amount` is updated based upon `additional_costs` in erpnext
    set_taxable_value(doc)
    set_taxes_and_totals(doc)

    validate_taxes(doc)
    update_valuation_rate(doc)


def set_taxes_and_totals(doc):
    set_item_wise_tax_rates(doc)
    set_total_taxes(doc)
