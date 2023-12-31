import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_months,
    cint,
    date_diff,
    flt,
    get_last_day,
    getdate,
)
from erpnext.accounts.utils import get_fiscal_year
from erpnext.assets.doctype.asset.asset import get_default_wdv_or_dd_depr_amount
from erpnext.assets.doctype.asset.depreciation import is_last_day_of_the_month


def get_wdv_or_dd_depr_amount(
    asset,
    fb_row,
    depreciable_value,
    schedule_idx,
    prev_depreciation_amount,
    has_wdv_or_dd_non_yearly_pro_rata,
):
    # As per IT act, if the asset is purchased in the 2nd half of fiscal year, then rate is divided by 2 for the first year

    if not fb_row.finance_book or not frappe.db.get_value(
        "Finance Book", fb_row.finance_book, "for_income_tax"
    ):
        return get_default_wdv_or_dd_depr_amount(
            asset,
            fb_row,
            depreciable_value,
            schedule_idx,
            prev_depreciation_amount,
            has_wdv_or_dd_non_yearly_pro_rata,
        )

    if not fb_row.daily_prorata_based:
        frappe.throw(
            _(
                "Please tick the 'Depreciate based on daily pro-rata' checkbox in the finance book row"
            )
        )

    asset.flags.wdv_it_act_applied = True

    rate_of_depreciation = fb_row.rate_of_depreciation

    start_date_of_next_fiscal_year = add_days(
        get_fiscal_year(asset.available_for_use_date)[2], 1
    )

    num_days_asset_used_in_fiscal_year = date_diff(
        start_date_of_next_fiscal_year, asset.available_for_use_date
    )
    if num_days_asset_used_in_fiscal_year <= 180:
        rate_of_depreciation = rate_of_depreciation / 2

    is_last_day = is_last_day_of_the_month(fb_row.depreciation_start_date)

    schedule_date = add_months(
        fb_row.depreciation_start_date,
        schedule_idx * cint(fb_row.frequency_of_depreciation),
    )
    if is_last_day:
        schedule_date = get_last_day(schedule_date)

    previous_schedule_date = add_months(
        schedule_date, -1 * cint(fb_row.frequency_of_depreciation)
    )
    if is_last_day:
        previous_schedule_date = get_last_day(previous_schedule_date)

    if fb_row.frequency_of_depreciation == 12:
        if schedule_date < start_date_of_next_fiscal_year:
            return flt(asset.gross_purchase_amount) * (flt(rate_of_depreciation) / 100)
        else:
            return (
                flt(depreciable_value)
                * (flt(fb_row.rate_of_depreciation) / 100)
                * (date_diff(schedule_date, previous_schedule_date) / 365)
            )
    elif fb_row.frequency_of_depreciation == 1:
        if schedule_date < start_date_of_next_fiscal_year:
            return (
                flt(asset.gross_purchase_amount)
                * (flt(rate_of_depreciation) / 100)
                * (
                    date_diff(schedule_date, previous_schedule_date)
                    / num_days_asset_used_in_fiscal_year
                )
            )
        else:
            return (
                flt(depreciable_value)
                * (flt(fb_row.rate_of_depreciation) / 100)
                * (date_diff(schedule_date, previous_schedule_date) / 365)
            )
    else:
        frappe.throw(_("Only monthly and yearly depreciations allowed yet."))


def cancel_depreciation_entries(asset, date):
    # Once the asset is sold during the current year, depreciation booked during the year of sale has to be cancelled as per Income Tax Act

    start_date_of_fiscal_year = get_fiscal_year(date)[1]

    for d in asset.get("schedules"):
        if getdate(d.schedule_date) < getdate(start_date_of_fiscal_year):
            continue

        frappe.get_doc("Journal Entry", d.journal_entry).cancel()
