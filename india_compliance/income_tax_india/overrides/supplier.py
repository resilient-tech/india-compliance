import frappe
from erpnext.accounts.services.payment_schedule import get_due_date
from frappe import _, bold
from frappe.utils import date_diff, getdate

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS, MSME_PAYMENT_TERMS_TEMPLATE
from india_compliance.income_tax_india.utils.msme import (
    get_msme_registration_details,
    get_msme_registration_for_pan,
    is_msme_covered,
)


def validate(doc, method=None):
    suggest_msme_registration(doc)
    validate_msme_pan(doc)
    validate_msme_payment_terms(doc)


def suggest_msme_registration(doc):
    if doc.msme_registration or not doc.pan or not (doc.is_new() or doc.has_value_changed("pan")):
        return

    msme_registration = get_msme_registration_for_pan(doc.pan)
    if not msme_registration:
        return

    frappe.msgprint(
        _("MSME Registration {0} has PAN {1}.").format(bold(msme_registration), bold(doc.pan)),
        title=_("MSME Registration Found"),
        indicator="blue",
        primary_action={
            "label": _("Link {0}").format(msme_registration),
            "client_action": "india_compliance.set_supplier_msme_registration",
            "args": {"supplier": doc.name, "msme_registration": msme_registration},
        },
    )


def validate_msme_pan(doc):
    if not doc.msme_registration or not doc.pan:
        return

    if not (doc.is_new() or doc.has_value_changed("pan") or doc.has_value_changed("msme_registration")):
        return

    registration_pan = frappe.db.get_value("MSME Registration", doc.msme_registration, "pan")
    if not registration_pan or registration_pan == doc.pan:
        return

    frappe.msgprint(
        _("PAN {0} does not match PAN {1} of MSME Registration {2}.").format(
            bold(doc.pan), bold(registration_pan), bold(doc.msme_registration)
        ),
        title=_("MSME PAN Mismatch"),
        indicator="orange",
    )


def validate_msme_payment_terms(doc):
    if not doc.msme_registration:
        return

    if not (
        doc.is_new()
        or doc.has_value_changed("payment_terms")
        or doc.has_value_changed("msme_registration")
        or doc.has_value_changed("supplier_group")
    ):
        return

    registration = get_msme_registration_details(doc.msme_registration)
    if not is_msme_covered(registration):
        return

    template = doc.payment_terms or frappe.db.get_value("Supplier Group", doc.supplier_group, "payment_terms")
    longest_days = template and get_longest_credit_days(template)

    if template and longest_days <= MSME_PAYMENT_DAYS:
        return

    if template:
        message = _(
            "Payment Terms {0} allow up to {1} days. Section 15 of the MSMED Act allows at most {2} days for this {3} enterprise."
        ).format(bold(template), longest_days, MSME_PAYMENT_DAYS, registration.enterprise_type)
    else:
        message = _(
            "This {0} enterprise has no Payment Terms, so its bills are due on the posting date."
        ).format(registration.enterprise_type)

    primary_action = None
    if frappe.db.exists("Payment Terms Template", MSME_PAYMENT_TERMS_TEMPLATE):
        primary_action = {
            "label": _("Use {0}").format(MSME_PAYMENT_TERMS_TEMPLATE),
            "client_action": "india_compliance.set_msme_payment_terms",
            "args": {"supplier": doc.name, "payment_terms": MSME_PAYMENT_TERMS_TEMPLATE},
        }
    else:
        message += " " + _("Set Payment Terms of {0} days or less.").format(MSME_PAYMENT_DAYS)

    frappe.msgprint(
        message,
        title=_("MSME Payment Terms"),
        indicator="orange",
        primary_action=primary_action,
    )


def get_longest_credit_days(template):
    terms = frappe.get_all(
        "Payment Terms Template Detail",
        filters={"parenttype": "Payment Terms Template", "parent": template},
        fields=["due_date_based_on", "credit_days", "credit_months"],
    )
    bill_dates = [getdate(f"2025-{month:02d}-01") for month in range(1, 13)]

    return max(
        (date_diff(get_due_date(term, bill_date), bill_date) for term in terms for bill_date in bill_dates),
        default=0,
    )
