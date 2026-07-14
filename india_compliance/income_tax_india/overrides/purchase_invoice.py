# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.utils import format_date, getdate, today

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.utils.msme import (
    get_msme_cancellation,
    get_msme_classification,
    get_msme_due_date,
)


# nosemgrep: frappe-semgrep-rules.rules.security.missing-argument-type-hint
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_valid_msme_registrations(
    doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
):
    """Registrations that covered a supply accepted on the posting date.

    Registered by then, and not cancelled before it - so a cancelled registration
    remains selectable on invoices backdated to when it was still valid.
    """
    posting_date = getdate((filters or {}).get("posting_date") or today())
    msme = frappe.qb.DocType("MSME Registration")

    return (
        frappe.qb.from_(msme)
        .select(msme.name, msme.registration_date)
        .where(msme.name.like(f"%{txt}%"))
        .where((msme.registration_date.isnull()) | (msme.registration_date <= posting_date))
        .where((msme.is_cancelled == 0) | (msme.cancelled_date >= posting_date))
        .orderby(msme.name)
        .limit(page_len)
        .offset(start)
    ).run()


@frappe.whitelist()
def get_msme_details(party_details: str | dict | frappe._dict):
    """The supplier's MSME registration, for seeding the transaction.

    Seeded on party change rather than with fetch_from, which re-derives on every
    save: the user must be able to clear it for a backdated invoice that predates
    the registration, or set another for one the supplier no longer holds.
    """
    party_details = frappe.parse_json(party_details)
    frappe.has_permission("Supplier", "read", throw=True)

    supplier = party_details.get("supplier")
    if not supplier:
        return {"msme_registration": None}

    return {
        "msme_registration": frappe.db.get_value("Supplier", supplier, "msme_registration"),
    }


def validate(doc, method=None):
    if not doc.msme_registration:
        return

    # a cancelled registration is not MSME, so the payment terms no longer apply
    if validate_msme_registration_status(doc):
        return

    validate_msme_payment_terms(doc)


def validate_msme_registration_status(doc) -> bool:
    """Advise when the registration did not cover this supply.

    The field is editable, so it may be set to a registration that was cancelled
    by the posting date, or that did not exist yet. Returns True in either case,
    so the caller can skip the 43B(h) payment terms.
    """
    registration_date = frappe.db.get_value("MSME Registration", doc.msme_registration, "registration_date")

    if registration_date and getdate(doc.posting_date) < getdate(registration_date):
        frappe.msgprint(
            _("MSME Registration {0} is registered on {1}, which is after the Posting Date.").format(
                bold(doc.msme_registration), bold(format_date(registration_date))
            ),
            title=_("MSME Registration Not Applicable"),
            indicator="orange",
        )
        return True

    cancellation = get_msme_cancellation(doc.msme_registration, doc.posting_date)
    if not cancellation:
        return False

    frappe.msgprint(
        _("MSME Registration {0} was cancelled on {1}.").format(
            bold(doc.msme_registration), bold(format_date(cancellation.cancelled_date))
        ),
        title=_("MSME Registration Cancelled"),
        indicator="orange",
    )

    return True


def validate_msme_payment_terms(doc):
    """Advise when the credit period exceeds the 45 days allowed u/s 43B(h).

    Non-blocking: agreeing to a longer credit period is legal, it only makes the
    unpaid amount disallowable if it is still outstanding at year end.
    """
    posting_date = getdate(doc.posting_date)
    classification = get_msme_classification(doc.msme_registration, posting_date)

    if not classification or not classification.msme_applicable:
        return

    due_date = get_effective_due_date(doc)
    msme_due_date = get_msme_due_date(posting_date)

    if not due_date or due_date <= msme_due_date:
        return

    frappe.msgprint(
        _("{0} is an MSME registered party. Due Date should be on or before {1} ({2} days).").format(
            bold(doc.supplier_name or doc.supplier),
            bold(format_date(msme_due_date)),
            MSME_PAYMENT_DAYS,
        ),
        title=_("Invalid Due Date"),
        indicator="orange",
    )


def get_effective_due_date(doc):
    """The last date by which the invoice must be fully paid."""
    if doc.payment_schedule:
        return max(getdate(row.due_date) for row in doc.payment_schedule if row.due_date)

    return getdate(doc.due_date) if doc.due_date else None
