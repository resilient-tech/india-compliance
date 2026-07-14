# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold
from frappe.utils import format_date, getdate

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.utils.msme import (
    get_msme_classification,
    get_msme_due_date,
)


def validate(doc, method=None):
    validate_msme_payment_terms(doc)


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
