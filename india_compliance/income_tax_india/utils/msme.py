# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.query_builder import Case
from frappe.utils import add_days, add_years, get_first_day, getdate, today

from india_compliance.income_tax_india.constants import FISCAL_YEAR_START_MONTH

UDYAM_NUMBER_REGEX = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")


def get_fiscal_year_dates(date=None) -> tuple:
    """(start_date, end_date) of the Indian income-tax FY containing a date."""
    date = getdate(date or today())
    months_from_start = (date.month - FISCAL_YEAR_START_MONTH) % 12
    start_date = get_first_day(date, d_months=-months_from_start)

    return start_date, add_days(add_years(start_date, 1), -1)


def get_indian_fiscal_year(date=None) -> str:
    start_date, end_date = get_fiscal_year_dates(date)
    return f"{start_date.year}-{end_date.year}"


def get_financial_year_dates(financial_year: str) -> tuple:
    start_year = int(financial_year.split("-")[0])
    return get_fiscal_year_dates(getdate(f"{start_year}-{FISCAL_YEAR_START_MONTH:02d}-01"))


def get_msme_registration_details(msme_registration: str, on_date=None) -> dict | None:
    if not msme_registration:
        return None

    on_date = getdate(on_date or today())
    msme = frappe.qb.DocType("MSME Registration")
    classification = frappe.qb.DocType("India MSME Classification")

    registrations = (
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
            Case()
            .when(msme.registration_date > on_date, 0)
            .when(msme.is_cancelled == 0, 1)
            .when(msme.cancelled_date >= on_date, 1)
            .else_(0)
            .as_("valid"),
        )
        .where(msme.name == msme_registration)
        .run(as_dict=True)
    )

    return registrations[0] if registrations else None


def is_msme_covered(registration) -> bool:
    return bool(
        registration
        and registration.valid
        and registration.enterprise_type in ("Micro", "Small")
        and registration.activity != "Trading"
    )


@frappe.whitelist()
def get_msme_registration_status(msme_registration: str) -> dict | None:
    frappe.has_permission("MSME Registration", "read", doc=msme_registration, throw=True)

    return get_msme_registration_details(msme_registration)


def get_msme_registration_for_pan(pan: str) -> str | None:
    registrations = frappe.get_all("MSME Registration", filters={"pan": pan}, pluck="name")

    return registrations[0] if len(registrations) == 1 else None
