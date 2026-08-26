# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.utils import format_date, getdate

from india_compliance.income_tax_india.utils.msme import (
    get_msme_due_date,
    get_msme_registration_details,
)


def validate(doc, method=None):
    if not doc.msme_registration:
        return

    posting_date = getdate(doc.posting_date)
    registration = get_msme_registration_details(doc.msme_registration, posting_date)

    if not registration:
        return

    if not registration.valid:
        frappe.msgprint(
            _("MSME Registration {0} was not valid on {1}, and has been removed.").format(
                bold(registration.name), bold(format_date(posting_date))
            ),
            title=_("Invalid MSME Registration"),
            indicator="orange",
        )
        doc.msme_registration = None
        return

    validate_msme_payment_terms(doc, registration, posting_date)


def validate_msme_payment_terms(doc, registration, posting_date):
    if doc.is_return or not registration.is_43b_applicable:
        return

    msme_due_date = get_msme_due_date(posting_date, doc.due_date, registration.not_written_agreement)

    if not doc.due_date or getdate(doc.due_date) <= msme_due_date:
        return

    frappe.msgprint(
        _("{0} is an MSME registered party. Due Date should be on or before {1} ({2} days).").format(
            bold(doc.supplier_name or doc.supplier),
            bold(format_date(msme_due_date)),
            (msme_due_date - posting_date).days,
        ),
        title=_("Invalid Due Date"),
        indicator="orange",
    )
