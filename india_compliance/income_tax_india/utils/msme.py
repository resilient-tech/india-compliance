# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import add_days, add_years, flt, format_date, get_first_day, getdate, today

from india_compliance.income_tax_india.constants import FISCAL_YEAR_START_MONTH, MSME_PAYMENT_DAYS

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

    registration = get_registrations_with_rows([msme_registration]).get(msme_registration)
    return registration and resolve_registration(registration, on_date)


def get_registrations_with_rows(names) -> dict:
    if not names:
        return {}

    registrations = {
        registration.name: registration
        for registration in frappe.get_all(
            "MSME Registration",
            filters={"name": ("in", names)},
            fields=["name", "registration_date", "is_cancelled", "cancelled_date"],
        )
    }

    for row in frappe.get_all(
        "India MSME Classification",
        filters={"parenttype": "MSME Registration", "parent": ("in", list(registrations))},
        fields=["parent", "financial_year", "enterprise_type", "activity"],
        order_by="financial_year desc",
    ):
        registrations[row.parent].setdefault("rows", []).append(row)

    return registrations


def resolve_registration(registration, on_date=None) -> frappe._dict:
    on_date = getdate(on_date or today())
    financial_year = get_indian_fiscal_year(on_date)
    row = next(
        (row for row in registration.get("rows", []) if row.financial_year <= financial_year),
        frappe._dict(),
    )

    return frappe._dict(
        name=registration.name,
        registration_date=registration.registration_date,
        is_cancelled=registration.is_cancelled,
        cancelled_date=registration.cancelled_date,
        enterprise_type=row.enterprise_type,
        activity=row.activity,
        carried_from=row.financial_year if row.financial_year != financial_year else None,
        valid=getdate(registration.registration_date) <= on_date
        and (
            not registration.is_cancelled
            or bool(registration.cancelled_date and getdate(registration.cancelled_date) >= on_date)
        ),
    )


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


def get_supplier_msme_details(supplier: str, on_date) -> dict | None:
    return get_msme_registration_details(
        frappe.db.get_value("Supplier", supplier, "msme_registration"), on_date
    )


def get_msme_payment_limit(doc):
    return add_days(getdate(doc.bill_date or doc.posting_date), MSME_PAYMENT_DAYS)


def get_coverage_label(registration) -> str:
    if not registration.valid:
        return _("Not valid on this date")
    if not registration.enterprise_type:
        return _("Category missing for this year")
    if registration.activity == "Trading":
        return _("Trader, not covered")
    if registration.enterprise_type not in ("Micro", "Small"):
        return _("{0}, not covered").format(_(registration.enterprise_type))
    if registration.carried_from:
        return _("Covered ({0}, carried from {1})").format(
            _(registration.enterprise_type), registration.carried_from
        )
    return _("Covered ({0})").format(_(registration.enterprise_type))


def resolve_msme_status(doc):
    return {"msme_status": get_msme_status(doc)}


def get_bill_suppliers(doc) -> list[str]:
    if doc.doctype != "Journal Entry":
        return [doc.supplier] if doc.get("supplier") else []

    return list(
        dict.fromkeys(
            row.party
            for row in doc.get("accounts") or []
            if row.party_type == "Supplier"
            and row.party
            and flt(row.credit_in_account_currency) > 0
            and not row.reference_name
        )
    )


def get_msme_status(doc):
    on_date = doc.get("bill_date") or doc.get("posting_date") or doc.get("transaction_date")
    statuses = []

    for supplier in get_bill_suppliers(doc):
        registration = get_supplier_msme_details(supplier, on_date)
        if not registration:
            continue

        if not is_msme_covered(registration):
            statuses.append(
                _("MSME Registration {0}: {1}").format(registration.name, get_coverage_label(registration))
            )
            continue

        status = _("MSME supplier ({0}) · {1}").format(_(registration.enterprise_type), registration.name)

        if doc.doctype == "Purchase Invoice":
            limit = get_msme_payment_limit(doc)
            pay_by = min(getdate(doc.due_date or doc.posting_date), limit)
            status += " · " + _("pay by {0}").format(format_date(pay_by))

        statuses.append(status)

    return "; ".join(statuses) or None
