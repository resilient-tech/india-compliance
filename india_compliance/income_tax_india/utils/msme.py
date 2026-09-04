# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import bulk_insert
from frappe.query_builder import Case
from frappe.utils import add_days, add_years, get_first_day, getdate, today

from india_compliance.income_tax_india.constants import FISCAL_YEAR_START_MONTH

# Section 15 MSMED Act: pay by the date agreed in writing, and in no case
# beyond 45 days. Where there is no written agreement at all, the limit is 15.
MSME_PAYMENT_DAYS = 45
MSME_PAYMENT_DAYS_WITHOUT_AGREEMENT = 15

# UDYAM registration number, e.g. UDYAM-MH-12-3456789 (19 characters)
UDYAM_NUMBER_REGEX = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")

# Only Micro and Small enterprises are covered by Section 43B(h); Medium is not.
MSME_APPLICABLE_TYPES = ("Micro", "Small")

# Registered, but unclassified for the year of supply. Reported rather than
# skipped, and untranslated like the stored enterprise types beside it.
MSME_UNCLASSIFIED = "Unclassified"

# Traders are registered on UDYAM only for Priority Sector Lending, and are
# excluded from Section 43B(h) (MSME Ministry OM dated 02-07-2021).
TRADING_ACTIVITY = "Trading"


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


def get_msme_due_date(posting_date, agreed_due_date=None, not_written_agreement=False):
    posting_date = getdate(posting_date)

    if not_written_agreement:
        return add_days(posting_date, MSME_PAYMENT_DAYS_WITHOUT_AGREEMENT)

    statutory_limit = add_days(posting_date, MSME_PAYMENT_DAYS)

    if not agreed_due_date or getdate(agreed_due_date) <= posting_date:
        return statutory_limit

    return min(getdate(agreed_due_date), statutory_limit)


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
            # A year with no classification row is assumed covered, as the reports
            # assume it: omitting a due payable to an MSME is the worse failure.
            Case()
            .when(classification.enterprise_type.isnull(), 1)
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
    """Carry each registration's year-end status into the years since.

    Users then only revisit the registrations that actually changed. Idempotent:
    a year that already has a row is left alone.

    Every missing year is filled, not just the last one - a run missed for a
    whole year would otherwise leave registrations unclassified, and an
    unclassified registration is invisible to every MSME report.
    """
    # a cancelled registration covers no new supplies, so carrying its
    # classification forward would only accrete rows no lookup can use
    registrations = frappe.get_all("MSME Registration", filters={"is_cancelled": 0}, pluck="name")
    if not registrations:
        return

    classifications = {}
    for row in frappe.get_all(
        "India MSME Classification",
        filters={"parenttype": "MSME Registration", "parent": ("in", registrations)},
        fields=[
            "parent",
            "financial_year",
            "to_date",
            "enterprise_type",
            "activity",
            "not_written_agreement",
        ],
    ):
        # a row without a period is invisible to every lookup, so it cannot be
        # the status a year ended on either
        if row.to_date:
            classifications.setdefault(row.parent, []).append(row)

    current_year_start = get_fiscal_year_dates()[0]
    new_rows = []

    for registration, rows in classifications.items():
        # a year still ahead says nothing about the years since: carry from the
        # last one that has actually ended
        ended_rows = [row for row in rows if getdate(row.to_date) < current_year_start]
        if not ended_rows:
            continue

        latest = max(ended_rows, key=lambda row: getdate(row.to_date))

        # the year ended with no row covering its last day: the status lapsed,
        # so there is nothing to carry
        if getdate(latest.to_date) != get_financial_year_dates(latest.financial_year)[1]:
            continue

        classified_years = {row.financial_year for row in rows}
        idx = len(rows)

        for financial_year in get_financial_years_between(
            add_days(getdate(latest.to_date), 1), current_year_start
        ):
            if financial_year in classified_years:
                continue

            idx += 1
            from_date, to_date = get_financial_year_dates(financial_year)

            new_row = frappe.new_doc("India MSME Classification")
            new_row.update(
                {
                    # bulk_insert writes rows as they are: it names nothing and
                    # runs no hooks
                    "name": frappe.generate_hash(length=10),
                    "parenttype": "MSME Registration",
                    "parentfield": "classifications",
                    "parent": registration,
                    "idx": idx,
                    "financial_year": financial_year,
                    # a row without a period is invisible to every lookup
                    "from_date": from_date,
                    "to_date": to_date,
                    "enterprise_type": latest.enterprise_type,
                    "activity": latest.activity,
                    "not_written_agreement": latest.not_written_agreement,
                }
            )

            new_rows.append(new_row)

    if new_rows:
        bulk_insert("India MSME Classification", new_rows)
