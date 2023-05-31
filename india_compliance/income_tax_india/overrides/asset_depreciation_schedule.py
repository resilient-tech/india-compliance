import frappe
from frappe import _
from frappe.utils import date_diff
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
    get_straight_line_or_manual_depr_amount,
    get_wdv_or_dd_depr_amount,
)


def get_depreciation_amount(
    asset,
    depreciable_value,
    row,
    schedule_idx=0,
    prev_depreciation_amount=0,
    has_wdv_or_dd_non_yearly_pro_rata=False,
):
    if row.depreciation_method in ("Straight Line", "Manual"):
        return get_straight_line_or_manual_depr_amount(asset, row)
    else:
        rate_of_depreciation = row.rate_of_depreciation
        # if its the first depreciation
        if depreciable_value == asset.gross_purchase_amount:
            if row.finance_book and frappe.db.get_value(
                "Finance Book", row.finance_book, "for_income_tax"
            ):
                # as per IT act, if the asset is purchased in the 2nd half of fiscal year, then rate is divided by 2
                diff = date_diff(
                    row.depreciation_start_date, asset.available_for_use_date
                )
                if diff <= 180:
                    rate_of_depreciation = rate_of_depreciation / 2
                    frappe.msgprint(
                        _(
                            "As per IT Act, the rate of depreciation for the first"
                            " depreciation entry is reduced by 50%."
                        )
                    )
        return get_wdv_or_dd_depr_amount(
            depreciable_value,
            rate_of_depreciation,
            row.frequency_of_depreciation,
            schedule_idx,
            prev_depreciation_amount,
            has_wdv_or_dd_non_yearly_pro_rata,
        )
