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
    is_last_day_of_the_month,
    month_diff,
)
from erpnext.accounts.utils import get_fiscal_year
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
    get_asset_depr_schedule_doc,
    get_default_wdv_or_dd_depr_amount,
)


def get_wdv_or_dd_depr_amount(
    asset,
    fb_row,
    depreciable_value,
    yearly_opening_wdv,
    schedule_idx,
    prev_depreciation_amount,
    has_wdv_or_dd_non_yearly_pro_rata,
    asset_depr_schedule,
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
            asset_depr_schedule,
        )

    asset_depr_schedule.flags.wdv_it_act_applied = True

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

    if schedule_idx == 0:
        previous_schedule_date = add_days(asset.available_for_use_date, -1)
    else:
        previous_schedule_date = add_months(
            schedule_date, -1 * cint(fb_row.frequency_of_depreciation)
        )
        if is_last_day:
            previous_schedule_date = get_last_day(previous_schedule_date)

    if fb_row.frequency_of_depreciation == 12:
        if schedule_date < start_date_of_next_fiscal_year:
            depreciation_amount = flt(asset.gross_purchase_amount) * (
                flt(rate_of_depreciation) / 100
            )
        else:
            depreciation_amount = flt(yearly_opening_wdv) * (
                flt(fb_row.rate_of_depreciation) / 100
            )
    elif fb_row.frequency_of_depreciation == 1:
        if fb_row.daily_prorata_based:
            if schedule_date >= start_date_of_next_fiscal_year:
                num_days_asset_used_in_fiscal_year = 365
            fraction = (
                date_diff(schedule_date, previous_schedule_date)
                / num_days_asset_used_in_fiscal_year
            )
        else:
            if schedule_date >= start_date_of_next_fiscal_year:
                fraction = 1 / 12
            else:
                no_of_months = month_diff(
                    get_fiscal_year(asset.available_for_use_date)[2],
                    asset.available_for_use_date,
                )
                fraction = 1 / no_of_months

        if schedule_date < start_date_of_next_fiscal_year:
            depreciation_amount = (
                flt(asset.gross_purchase_amount)
                * (flt(rate_of_depreciation) / 100)
                * fraction
            )
        else:
            depreciation_amount = (
                flt(yearly_opening_wdv)
                * (flt(fb_row.rate_of_depreciation) / 100)
                * fraction
            )
    else:
        frappe.throw(_("Only monthly and yearly depreciations allowed yet."))

    return depreciation_amount


def cancel_depreciation_entries(asset_doc, date):
    # Once the asset is sold during the current year, depreciation booked during the year of sale has to be cancelled as per Income Tax Act

    start_date_of_fiscal_year = get_fiscal_year(date)[1]

    fb_for_income_tax_map = dict(
        frappe.db.get_all("Finance Book", ["name", "for_income_tax"], as_list=True)
    )

    for row in asset_doc.get("finance_books"):
        if not row.finance_book:
            return

        if not fb_for_income_tax_map[row.finance_book]:
            continue

        asset_depr_schedule_doc = get_asset_depr_schedule_doc(
            asset_doc.name, "Active", row.finance_book
        )

        for d in asset_depr_schedule_doc.get("depreciation_schedule"):
            if getdate(d.schedule_date) < getdate(start_date_of_fiscal_year):
                continue

            frappe.get_doc("Journal Entry", d.journal_entry).cancel()
