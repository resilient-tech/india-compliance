import frappe
from frappe import _
from frappe.utils import date_diff


def get_updated_rate_of_depreciation_for_wdv_and_dd(asset, depreciable_value, fb_row):
    rate_of_depreciation = fb_row.rate_of_depreciation
    # if its the first depreciation
    if depreciable_value == asset.gross_purchase_amount:
        if fb_row.finance_book and frappe.db.get_value(
            "Finance Book", fb_row.finance_book, "for_income_tax"
        ):
            # as per IT act, if the asset is purchased in the 2nd half of fiscal year, then rate is divided by 2
            diff = date_diff(
                fb_row.depreciation_start_date, asset.available_for_use_date
            )
            if diff <= 180:
                rate_of_depreciation = rate_of_depreciation / 2
                frappe.msgprint(
                    _(
                        "As per IT Act, the rate of depreciation for the first"
                        " depreciation entry is reduced by 50%."
                    )
                )

    return rate_of_depreciation
