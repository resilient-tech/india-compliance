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
)
from erpnext.assets.doctype.asset_depreciation_schedule.depreciation_methods import (
    WDVMethod,
)


def get_wdv_or_dd_depr_amount(asset_depreciation_schedule, row_idx):

    # As per IT act, if the asset is purchased in the 2nd half of fiscal year, then rate is divided by 2 for the first year
    if not asset_depreciation_schedule.fb_row.finance_book or not frappe.db.get_value(
        "Finance Book",
        asset_depreciation_schedule.fb_row.finance_book,
        "for_income_tax",
    ):
        return WDVMethod.calculate_wdv_or_dd_based_depreciation_amount(
            asset_depreciation_schedule, row_idx
        )

    asset_depreciation_schedule.flags.wdv_it_act_applied = True
    rate_of_depreciation = asset_depreciation_schedule.fb_row.rate_of_depreciation

    start_date_of_next_fiscal_year = add_days(
        get_fiscal_year(asset_depreciation_schedule.asset_doc.available_for_use_date)[
            2
        ],
        1,
    )

    num_days_asset_used_in_fiscal_year = date_diff(
        start_date_of_next_fiscal_year,
        asset_depreciation_schedule.asset_doc.available_for_use_date,
    )
    if num_days_asset_used_in_fiscal_year <= 180:
        rate_of_depreciation = rate_of_depreciation / 2

    is_last_day = is_last_day_of_the_month(
        asset_depreciation_schedule.fb_row.depreciation_start_date
    )

    schedule_date = add_months(
        asset_depreciation_schedule.fb_row.depreciation_start_date,
        row_idx * cint(asset_depreciation_schedule.fb_row.frequency_of_depreciation),
    )
    if is_last_day:
        schedule_date = get_last_day(schedule_date)

    schedule_date = getdate(schedule_date)

    if row_idx == 0:
        previous_schedule_date = add_days(
            asset_depreciation_schedule.asset_doc.available_for_use_date, -1
        )
    else:
        previous_schedule_date = add_months(
            schedule_date,
            -1 * cint(asset_depreciation_schedule.fb_row.frequency_of_depreciation),
        )
        if is_last_day:
            previous_schedule_date = get_last_day(previous_schedule_date)

    if asset_depreciation_schedule.fb_row.frequency_of_depreciation == 12:
        if schedule_date < start_date_of_next_fiscal_year:
            depreciation_amount = flt(
                asset_depreciation_schedule.asset_doc.net_purchase_amount
            ) * (flt(rate_of_depreciation) / 100)
        else:
            depreciation_amount = flt(
                asset_depreciation_schedule.yearly_opening_wdv
            ) * (flt(asset_depreciation_schedule.fb_row.rate_of_depreciation) / 100)
            # if leap year, then consider 366 days
            if (
                is_leap_year(cint(schedule_date.year))
                and asset_depreciation_schedule.fb_row.daily_prorata_based
            ):
                depreciation_amount = depreciation_amount * 366 / 365
    elif asset_depreciation_schedule.fb_row.frequency_of_depreciation == 1:
        if asset_depreciation_schedule.fb_row.daily_prorata_based:
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
                    get_fiscal_year(
                        asset_depreciation_schedule.asset_doc.available_for_use_date
                    )[2],
                    asset_depreciation_schedule.asset_doc.available_for_use_date,
                )
                fraction = 1 / no_of_months

        if schedule_date < start_date_of_next_fiscal_year:
            depreciation_amount = (
                flt(asset_depreciation_schedule.asset_doc.net_purchase_amount)
                * (flt(rate_of_depreciation) / 100)
                * fraction
            )
        else:
            depreciation_amount = (
                flt(asset_depreciation_schedule.yearly_opening_wdv)
                * (flt(asset_depreciation_schedule.fb_row.rate_of_depreciation) / 100)
                * fraction
            )
    else:
        frappe.throw(_("Only monthly and yearly depreciations allowed yet."))

    return depreciation_amount


def is_leap_year(year):
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


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

            if d.journal_entry:
                frappe.get_doc("Journal Entry", d.journal_entry).cancel()
