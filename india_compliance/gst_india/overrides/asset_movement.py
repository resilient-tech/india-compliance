import json

import frappe
from erpnext.accounts.party import get_address_tax_category
from erpnext.assets.doctype.asset.asset import get_asset_value_after_depreciation
from frappe.utils import flt

from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.subcontracting_transaction import (
    ignore_gst_validations_for_subcontracting,
    is_e_waybill_applicable,
    set_address_display,
    set_default_item_tax_template,
)
from india_compliance.gst_india.overrides.subcontracting_transaction import (
    validate as subcontracting_validate,
)
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import CustomTaxController


def onload(doc, method=None):
    set_address_display(doc)

    # For e-Waybill data mapping
    doc.company_gstin = doc.bill_from_gstin
    doc.supplier_gstin = doc.bill_to_gstin
    doc.gst_category = doc.bill_to_gst_category

    if not doc.get("ewaybill"):
        return

    if is_e_waybill_applicable(doc) and (e_waybill_info := get_e_waybill_info(doc)):
        doc.set_onload("e_waybill_info", e_waybill_info)


def validate(doc, method=None):
    # Item Tax Templates and taxable values feed the tax calculation in subcontracting_validate
    if is_e_waybill_applicable(doc) and not ignore_gst_validations_for_subcontracting(doc):
        set_default_item_tax_template(doc, _get_tax_category(doc))
        set_taxable_value(doc)

    subcontracting_validate(doc)


def _get_tax_category(doc):
    return doc.get("tax_category") or get_address_tax_category(
        None, doc.get("bill_to_address"), doc.get("ship_to_address")
    )


@frappe.whitelist()
def update_item_tax_template(doc: str):

    doc = json.loads(doc, object_hook=frappe._dict)
    set_default_item_tax_template(doc, _get_tax_category(doc), force=True)
    CustomTaxController(doc).set_item_wise_tax_rates()

    frappe.response.docs.append(doc)


def set_taxable_value(doc):

    for row in doc.assets:
        if row.taxable_value or not row.asset:
            continue

        row.taxable_value = flt(get_asset_value_after_depreciation(row.asset), row.precision("taxable_value"))


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Asset Movement",
        data,
        "e-Waybill Log",
        "Integration Request",
    )
