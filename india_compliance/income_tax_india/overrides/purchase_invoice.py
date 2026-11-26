import frappe
from frappe import _, bold
from frappe.utils import format_date, getdate

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.utils.msme import (
    get_msme_payment_limit,
    get_supplier_msme_details,
    is_msme_covered,
)


def validate(doc, method=None):
    validate_msme_due_date(doc)


def validate_msme_due_date(doc):
    if doc.is_return or not doc.due_date or doc.docstatus != 0:
        return

    if not (
        doc.is_new()
        or doc.has_value_changed("due_date")
        or doc.has_value_changed("bill_date")
        or doc.has_value_changed("posting_date")
        or doc.has_value_changed("supplier")
    ):
        return

    limit = get_msme_payment_limit(doc)
    if getdate(doc.due_date) <= limit:
        return

    registration = get_supplier_msme_details(doc.supplier, doc.bill_date or doc.posting_date)
    if not is_msme_covered(registration):
        return

    frappe.msgprint(
        _(
            "{0} is a {1} enterprise. Section 15 of the MSMED Act requires payment within {2} days, by {3}; this bill is due on {4}."
        ).format(
            bold(doc.supplier_name or doc.supplier),
            registration.enterprise_type,
            MSME_PAYMENT_DAYS,
            bold(format_date(limit)),
            format_date(doc.due_date),
        ),
        title=_("MSME Due Date"),
        indicator="orange",
        primary_action={
            "label": _("Set Due Date to {0}").format(format_date(limit)),
            "client_action": "india_compliance.set_msme_due_date",
            "args": {"purchase_invoice": doc.name, "due_date": str(limit)},
        },
    )
