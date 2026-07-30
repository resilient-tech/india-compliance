from erpnext.assets.doctype.asset.asset import get_asset_value_after_depreciation
from frappe.utils import flt

from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import is_indian_registered_company


def validate(doc, method=None):
    set_taxable_value(doc)


def set_taxable_value(doc):
    """
    Default the taxable value to the Asset's Value After Depreciation, since used
    capital goods are usually moved at their written down value, and not at cost.
    """
    if not is_indian_registered_company(doc):
        return

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
