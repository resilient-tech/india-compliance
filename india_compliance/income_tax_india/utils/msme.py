# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import collections

import frappe
from frappe.utils import add_days, add_years, get_first_day, getdate, today

from india_compliance.income_tax_india.constants import (
    FISCAL_YEAR_START_MONTH,
    MSME_APPLICABLE_TYPES,
    MSME_PAYMENT_DAYS,
    TRADING_ACTIVITY,
)


def get_fiscal_year_dates(date=None) -> tuple:
    """(start_date, end_date) of the Indian income-tax FY containing a date.

    The FY definition lives here alone; every other helper derives from these
    dates, so a change to the statutory year does not have to be chased across
    the app.
    """
    date = getdate(date or today())

    # months elapsed since the FY began; negative before the start month, in
    # which case the date still belongs to the FY that began the previous year
    months_from_start = (date.month - FISCAL_YEAR_START_MONTH) % 12
    start_date = get_first_day(date, d_months=-months_from_start)

    return start_date, add_days(add_years(start_date, 1), -1)


def get_indian_fiscal_year(date=None) -> str:
    """Indian income-tax FY for a date, e.g. "2024-2025"."""
    start_date, end_date = get_fiscal_year_dates(date)
    return f"{start_date.year}-{end_date.year}"


def get_financial_year_dates(financial_year: str) -> tuple:
    """(start_date, end_date) of an FY named like "2024-2025"."""
    start_year = int(financial_year.split("-")[0])

    # any date inside the FY resolves it; its start month is the FY's own
    return get_fiscal_year_dates(getdate(f"{start_year}-{FISCAL_YEAR_START_MONTH:02d}-01"))


def get_msme_due_date(posting_date):
    """MSME payment due date: posting date (treated as date of acceptance) + 45 days."""
    return add_days(getdate(posting_date), MSME_PAYMENT_DAYS)


def is_section_43_b_msme_applicable(enterprise_type, activity) -> bool:
    """Section 43B(h) applies only to Micro/Small enterprises that are not traders."""
    return bool(enterprise_type in MSME_APPLICABLE_TYPES and activity != TRADING_ACTIVITY)


def get_msme_registration_details(msme_registration: str, on_date=None) -> dict | None:
    """
    The registration, with whatever it was classified as on a date.
    """
    if not msme_registration:
        return None

    msme = frappe.qb.DocType("MSME Registration")
    registrations = (
        get_msme_registration_query(getdate(on_date or today()))
        .where(msme.name == msme_registration)
        .run(as_dict=True)
    )

    return registrations[0] if registrations else None


def get_msme_registration_query(on_date):
    msme = frappe.qb.DocType("MSME Registration")
    classification = frappe.qb.DocType("India MSME Classification")

    return (
        frappe.qb.from_(msme)
        .left_join(classification)
        .on(
            (classification.parent == msme.name)
            & (classification.parenttype == "MSME Registration")
            & (classification.financial_year == get_indian_fiscal_year(on_date))
        )
        .select(
            msme.name,
            msme.registration_date,
            msme.is_cancelled,
            msme.cancelled_date,
            classification.enterprise_type,
            classification.activity,
            classification.not_written_agreement,
            # covered the supply: granted by then, and not cancelled before it
            Case()
            .when(msme.registration_date > on_date, 0)
            .when(msme.is_cancelled == 0, 1)
            .when(msme.cancelled_date >= on_date, 1)
            .else_(0)
            .as_("valid"),
            # Section 43B(h) reaches Micro/Small enterprises that are not traders.
            # Matched positively, so a year with no classification row at all -
            # every column NULL - is not applicable either.
            Case()
            .when(
                classification.enterprise_type.isin(MSME_APPLICABLE_TYPES)
                & (classification.activity != TRADING_ACTIVITY),
                1,
            )
            .else_(0)
            .as_("is_43b_applicable"),
        )
    )


def get_financial_years_between(from_date, to_date) -> list[str]:
    """Indian FY strings spanned by a date range, e.g. ["2023-2024", "2024-2025"]."""
    financial_years = []
    date = get_fiscal_year_dates(from_date)[0]
    to_date = getdate(to_date)

    while date <= to_date:
        financial_years.append(get_indian_fiscal_year(date))
        date = add_years(date, 1)

    return financial_years


@frappe.whitelist()
def get_msme_registration_status(msme_registration: str) -> dict | None:
    """One registration as it stands today, for display beside the field."""
    frappe.has_permission("MSME Registration", "read", throw=True)

    return get_msme_registration_details(msme_registration)


@frappe.whitelist()
def get_msme_registration_options(posting_date: str | None = None) -> list[dict]:
    """Every registration, described as it stood on the supply date.

    Invalid ones are offered too: the user decides, and the description says why
    it did not cover the supply.
    """
    frappe.has_permission("MSME Registration", "read", throw=True)

    posting_date = getdate(posting_date or today())
    msme = frappe.qb.DocType("MSME Registration")
    options = []

    for registration in get_msme_registration_query(posting_date).orderby(msme.name).run(as_dict=True):
        description = []

        if registration.enterprise_type:
            description.append(f"{_(registration.enterprise_type)} - {_(registration.activity)}")

        if not registration.valid:
            description.append(_("Invalid"))

        options.append(
            {
                "value": registration.name,
                "description": ", ".join(description) or _("Not Classified"),
            }
        )

    return options


def update_msme_classification():
    """Carry classifications forward into the new FY, so users only update the
    registrations that actually changed. Idempotent: never overwrites a year
    that is already classified.
    """
    start_date = get_fiscal_year_dates()[0]
    new_fy = get_indian_fiscal_year(start_date)
    prev_fy = get_indian_fiscal_year(add_years(start_date, -1))

    prev_rows = frappe.get_all(
        "India MSME Classification",
        filters={"parenttype": "MSME Registration", "financial_year": prev_fy},
        fields=["parent", "enterprise_type", "activity"],
    )
    if not prev_rows:
        return

    # a cancelled registration covers no new supplies, so carrying its
    # classification forward would only accrete rows no lookup can use
    cancelled = set(
        frappe.get_all(
            "MSME Registration",
            filters={"name": ("in", [row.parent for row in prev_rows]), "is_cancelled": 1},
            pluck="name",
        )
    )

    classified = set(
        frappe.get_all(
            "India MSME Classification",
            filters={"parenttype": "MSME Registration", "financial_year": new_fy},
            pluck="parent",
        )
    )

    # idx continues after the rows the registration already has
    row_count = collections.Counter(
        frappe.get_all(
            "India MSME Classification",
            filters={"parenttype": "MSME Registration", "parent": ("in", [row.parent for row in prev_rows])},
            pluck="parent",
        )
    )

    for row in prev_rows:
        if row.parent in classified or row.parent in cancelled:
            continue

        new_row = frappe.new_doc("India MSME Classification")
        new_row.update(
            {
                "parenttype": "MSME Registration",
                "parentfield": "classifications",
                "parent": row.parent,
                "idx": row_count[row.parent] + 1,
                "financial_year": new_fy,
                "enterprise_type": row.enterprise_type,
                "activity": row.activity,
            }
        )

        # db_insert bypasses the document hooks, and a row without a period is
        # invisible to every lookup
        new_row.set_period()
        new_row.db_insert()
