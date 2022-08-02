import frappe
from frappe import _
from frappe.utils import date_diff, flt


def get_depreciation_amount(asset, depreciable_value, row):
    if row.depreciation_method in ("Straight Line", "Manual"):
        # if the Depreciation Schedule is being prepared for the first time
        if not asset.flags.increase_in_asset_life:
            depreciation_amount = (
                flt(asset.gross_purchase_amount)
                - flt(row.expected_value_after_useful_life)
            ) / flt(row.total_number_of_depreciations)

        # if the Depreciation Schedule is being modified after Asset Repair
        else:
            depreciation_amount = (
                flt(row.value_after_depreciation)
                - flt(row.expected_value_after_useful_life)
            ) / (date_diff(asset.to_date, asset.available_for_use_date) / 365)

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

        depreciation_amount = flt(depreciable_value * (flt(rate_of_depreciation) / 100))

    return depreciation_amount
