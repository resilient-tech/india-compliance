# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import collections

import frappe
from frappe.utils import add_days, add_years, flt, get_first_day, getdate, today

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


def get_msme_classification(msme_registration: str, on_date=None) -> dict | None:
    """Classification of a registration as on a date (default: today).

    None = not MSME on that date: either unclassified for the year, or the
    registration was already cancelled.
    """
    if not msme_registration:
        return None

    on_date = getdate(on_date or today())

    if is_msme_registration_cancelled(msme_registration, on_date):
        return None

    classification = frappe.db.get_value(
        "India MSME Classification",
        {
            "parenttype": "MSME Registration",
            "parent": msme_registration,
            "from_date": ("<=", on_date),
            "to_date": (">=", on_date),
        },
        ["enterprise_type", "activity"],
        as_dict=True,
    )

    if classification:
        classification.msme_applicable = is_section_43_b_msme_applicable(
            classification.enterprise_type, classification.activity
        )

    return classification


def get_msme_cancellation(msme_registration: str, on_date) -> dict | None:
    """The registration's cancellation, if it applies to a supply on ``on_date``.

    None = still registered on that date. Otherwise the MSME row, so callers can
    report *when* it was cancelled.
    """
    registration = frappe.db.get_value(
        "MSME Registration", msme_registration, ["is_cancelled", "cancelled_date"], as_dict=True
    )
    if not registration or not registration.is_cancelled:
        return None

    # a cancelled registration with no date on record is treated as never valid
    if not registration.cancelled_date:
        return registration

    if getdate(on_date) > getdate(registration.cancelled_date):
        return registration


def is_msme_registration_cancelled(msme_registration: str, on_date) -> bool:
    """A supply accepted after cancellation is not from an MSME."""
    return bool(get_msme_cancellation(msme_registration, on_date))


def get_classification_map(
    registrations: list[str], financial_years: list[str] | None = None
) -> dict[tuple, dict]:
    """Bulk-load classification rows, keyed by (msme_registration, fy).

    Pass ``financial_years`` to fetch only the years actually needed (e.g. the
    FYs spanned by the invoices under report) instead of every year on record.
    """
    filters = {"parenttype": "MSME Registration", "parent": ("in", registrations)}
    if financial_years:
        filters["financial_year"] = ("in", financial_years)

    rows = frappe.get_all(
        "India MSME Classification",
        filters=filters,
        fields=["parent as msme_registration", "financial_year", "enterprise_type", "activity"],
    )
    return {(row.msme_registration, row.financial_year): row for row in rows}


def get_financial_years_between(from_date, to_date) -> list[str]:
    """Indian FY strings spanned by a date range, e.g. ["2023-2024", "2024-2025"]."""
    financial_years = []
    date = get_fiscal_year_dates(from_date)[0]
    to_date = getdate(to_date)

    while date <= to_date:
        financial_years.append(get_indian_fiscal_year(date))
        date = add_years(date, 1)

    return financial_years


def get_settlement_summary(settlements, due_date, from_date=None, to_date=None) -> dict:
    """Split settlement amounts into paid-on-time vs paid-late vs the due date.

    Pass ``from_date``/``to_date`` to count only settlements posted within a
    window (e.g. Form-1's half-year reporting period).
    """
    paid_on_time = paid_late = 0
    for settlement in settlements:
        posting_date = settlement["posting_date"]
        if from_date and posting_date < from_date:
            continue
        if to_date and posting_date > to_date:
            continue

        if posting_date <= due_date:
            paid_on_time += settlement["amount"]
        else:
            paid_late += settlement["amount"]

    return {"paid_on_time": paid_on_time, "paid_late": paid_late}


def get_payable_ledger_groups(company, suppliers, as_on_date) -> dict[tuple, dict]:
    """All Payable ledger entries for the suppliers as on a date, grouped by
    the voucher they settle - the same grouping ERPNext's Accounts Payable
    report uses, so every payable voucher type (Purchase Invoice, Journal
    Entry, ...) is covered, not just Purchase Invoices.

    Each group carries the voucher's own (anchor) entry, the settlement
    entries against it, and the signed balance: positive = amount payable,
    negative = unadjusted payment / credit note. Amounts are company currency.
    """
    ple = frappe.qb.DocType("Payment Ledger Entry")
    entries = (
        frappe.qb.from_(ple)
        .select(
            ple.against_voucher_type,
            ple.against_voucher_no,
            ple.party,
            ple.voucher_type,
            ple.voucher_no,
            ple.posting_date,
            ple.amount,
        )
        .where(ple.delinked == 0)
        .where(ple.account_type == "Payable")
        .where(ple.party_type == "Supplier")
        .where(ple.company == company)
        .where(ple.party.isin(suppliers))
        .where(ple.posting_date <= getdate(as_on_date))
    ).run(as_dict=True)

    groups: dict[tuple, dict] = {}
    for entry in entries:
        group = groups.setdefault(
            (entry.against_voucher_type, entry.against_voucher_no),
            frappe._dict(party=entry.party, anchor=None, settlements=[], balance=0),
        )
        group.balance += entry.amount

        is_anchor = (
            entry.voucher_type == entry.against_voucher_type and entry.voucher_no == entry.against_voucher_no
        )
        if is_anchor:
            group.anchor = entry
        else:
            group.settlements.append({"posting_date": getdate(entry.posting_date), "amount": -entry.amount})

    return groups


def get_msme_payables(
    company: str,
    to_date,
    from_date=None,
    supplier: str | None = None,
    as_on_date=None,
    enterprise_type: str | None = None,
    only_43b_applicable=False,
    settlement_from_date=None,
) -> list[dict]:
    """
    Shared MSME payables dataset for the 43B(h) and Form-1 reports, returned
    as complete report-ready rows (single pass per payable voucher).

    Built directly on the Payment Ledger, covering every payable voucher type.
    Unadjusted payments / credit notes are returned as NEGATIVE rows so the net
    total reconciles with GL / Accounts Payable.

    - only_43b_applicable: only Micro/Small non-trader suppliers
    - enterprise_type: narrows further to one type (e.g. Micro vs Small);
    - settlement_from_date: window start for the paid_within_due /
      paid_after_due split (e.g. Form-1 counts only payments made during the
      half-year);
    """
    as_on_date = getdate(as_on_date or to_date)
    from_date = getdate(from_date) if from_date else None
    to_date = getdate(to_date)

    supplier_filters = {"msme_registration": ("is", "set")}
    if supplier:
        supplier_filters["name"] = supplier

    supplier_details = {
        d.name: d
        for d in frappe.get_all(
            "Supplier",
            filters=supplier_filters,
            fields=["name", "supplier_name", "pan", "msme_registration"],
        )
    }
    if not supplier_details:
        return []

    groups = get_payable_ledger_groups(company, list(supplier_details), as_on_date)

    # anchorless groups have no payable voucher as on date (e.g. allocations
    # of a future-dated voucher)
    anchored = {}
    for key, group in groups.items():
        if not group.anchor:
            continue

        posting_date = getdate(group.anchor.posting_date)

        # dues are range-bound (each year disallows its own accruals), but an
        # unadjusted credit nets the payable regardless of when it was posted -
        # this keeps the report's net total reconciled with GL / Accounts Payable
        if group.anchor.amount > 0:
            if posting_date > to_date or (from_date and posting_date < from_date):
                continue

        anchored[key] = group

    if not anchored:
        return []

    financial_years = get_financial_years_between(
        min(getdate(g.anchor.posting_date) for g in anchored.values()),
        as_on_date,
    )
    classification_map = get_classification_map(
        registrations=list({d.msme_registration for d in supplier_details.values()}),
        financial_years=financial_years,
    )

    records = []
    for (voucher_type, voucher_no), group in anchored.items():
        posting_date = getdate(group.anchor.posting_date)
        details = supplier_details[group.party]
        fy = get_indian_fiscal_year(posting_date)

        # Applicability is derived at read time (single source of truth), so
        # reports stay correct even if a persisted child-row flag is stale.
        classification = None
        if row := classification_map.get((details.msme_registration, fy)):
            classification = {
                "enterprise_type": row.enterprise_type,
                "msme_applicable": is_section_43_b_msme_applicable(row.enterprise_type, row.activity),
            }

        if not is_classification_included(classification, enterprise_type, only_43b_applicable):
            continue

        due_date = get_msme_due_date(posting_date)
        record = {
            "supplier": group.party,
            "supplier_name": details.supplier_name,
            "pan": details.pan,
            # the registration is named after the UDYAM number
            "udyam_number": details.msme_registration,
            "enterprise_type": classification["enterprise_type"],
            "voucher_type": voucher_type,
            "voucher_no": voucher_no,
            "posting_date": posting_date,
            "financial_year": fy,
            "due_date": due_date,
        }

        # 43B(h) amounts only apply to Micro/Small non-traders, even when a
        # caller fetches the unfiltered dataset
        msme_applicable = classification["msme_applicable"]

        if group.anchor.amount > 0:
            record.update(
                get_due_voucher_amounts(group, due_date, as_on_date, msme_applicable, settlement_from_date)
            )
        else:
            # unadjusted payment / credit note: reduces the net amount payable
            unadjusted = flt(min(group.balance, 0))
            if not unadjusted:
                continue

            record.update(
                {
                    "invoice_amount": flt(group.anchor.amount),
                    "paid_amount": 0,
                    "paid_within_due": 0,
                    "paid_after_due": 0,
                    "outstanding": unadjusted,
                    "outstanding_not_due": 0,
                    "outstanding_overdue": 0,
                    "disallowable_amount": unadjusted if msme_applicable else 0,
                    "payment_status": (
                        "Unadjusted Advance" if voucher_type == "Payment Entry" else "Unadjusted Credit"
                    ),
                    "days_overdue": 0,
                    "payment_date": None,
                }
            )

        records.append(record)

    records.sort(key=lambda record: (record["supplier"], record["posting_date"]))
    return records


def get_due_voucher_amounts(group, due_date, as_on_date, msme_applicable, settlement_from_date=None) -> dict:
    summary = get_settlement_summary(group.settlements, due_date)
    settled_total = summary["paid_on_time"] + summary["paid_late"]

    # the windowed split (e.g. Form-1's half-year) only differs from the
    # full split when a window start is given
    if settlement_from_date:
        window = get_settlement_summary(group.settlements, due_date, from_date=settlement_from_date)
    else:
        window = summary

    outstanding = max(flt(group.balance), 0)
    is_overdue = as_on_date > due_date

    if outstanding <= 0:
        payment_status = "Paid Late" if summary["paid_late"] > 0 else "Paid On Time"
    elif is_overdue:
        payment_status = "Unpaid - Overdue"
    else:
        payment_status = "Within Due Date"

    return {
        "invoice_amount": flt(group.anchor.amount),
        "paid_amount": flt(settled_total),
        "paid_within_due": flt(window["paid_on_time"]),
        "paid_after_due": flt(window["paid_late"]),
        "outstanding": outstanding,
        "outstanding_not_due": 0 if is_overdue else outstanding,
        "outstanding_overdue": outstanding if is_overdue else 0,
        # paid in-year is allowed in that year; only the unpaid overdue
        # portion is added back u/s 43B(h)
        "disallowable_amount": outstanding if (is_overdue and msme_applicable) else 0,
        "payment_status": payment_status,
        "days_overdue": (as_on_date - due_date).days if is_overdue else 0,
        "payment_date": max((s["posting_date"] for s in group.settlements), default=None),
    }


def is_classification_included(classification, enterprise_type, only_43b_applicable) -> bool:
    # no classification row for the invoice's FY = not MSME-registered that year
    if classification is None:
        return False

    if only_43b_applicable and not classification["msme_applicable"]:
        return False

    # enterprise_type narrows within the above; it never widens past it
    if enterprise_type and classification["enterprise_type"] != enterprise_type:
        return False

    return True


def update_msme_classification():
    """Carry classifications forward into the new FY, so users only update the
    registrations that actually changed. Idempotent: never overwrites a year
    that is already classified.
    """
    from_date, to_date = get_fiscal_year_dates()
    new_fy = get_indian_fiscal_year(from_date)
    prev_fy = get_indian_fiscal_year(add_years(from_date, -1))

    prev_rows = frappe.get_all(
        "India MSME Classification",
        filters={"parenttype": "MSME Registration", "financial_year": prev_fy},
        fields=["parent", "enterprise_type", "activity"],
    )
    if not prev_rows:
        return

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
        if row.parent in classified:
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
                "from_date": from_date,
                "to_date": to_date,
            }
        )
        new_row.db_insert()
