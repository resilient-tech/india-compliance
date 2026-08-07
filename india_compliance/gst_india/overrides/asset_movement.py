from erpnext.assets.doctype.asset.asset import get_asset_value_after_depreciation
from frappe.utils import flt

from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.subcontracting_transaction import (
    ignore_gst_validations_for_subcontracting,
    is_e_waybill_applicable,
    set_address_display,
)
from india_compliance.gst_india.overrides.subcontracting_transaction import (
    validate as subcontracting_validate,
)
from india_compliance.gst_india.utils import is_inward_transaction
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info


def onload(doc, method=None):
    set_address_display(doc)

    # company_gstin is refered as generator of e-waybill
    if is_inward_transaction(doc):
        doc.company_gstin, doc.supplier_gstin = doc.bill_to_gstin, doc.bill_from_gstin
        doc.gst_category = doc.bill_from_gst_category
    else:
        doc.company_gstin, doc.supplier_gstin = doc.bill_from_gstin, doc.bill_to_gstin
        doc.gst_category = doc.bill_to_gst_category

    doc.posting_date = doc.transaction_date
    doc.items = doc.assets

    if not doc.get("ewaybill"):
        return

    if is_e_waybill_applicable(doc) and (e_waybill_info := get_e_waybill_info(doc)):
        doc.set_onload("e_waybill_info", e_waybill_info)


def validate(doc, method=None):
    # Taxable values feed the tax calculation in subcontracting_validate
    if is_e_waybill_applicable(doc) and not ignore_gst_validations_for_subcontracting(doc):
        set_taxable_value(doc)

    subcontracting_validate(doc)


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
