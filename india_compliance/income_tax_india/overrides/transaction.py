import frappe
from frappe import _, bold
from frappe.utils import add_days, date_diff, format_date, getdate

from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.utils.msme import (
    get_bill_suppliers,
    get_msme_payment_limit,
    get_supplier_msme_details,
    is_msme_covered,
)


def validate_msme_due_date(doc, method=None):
    if doc.get("is_return") or not doc.get("due_date") or doc.docstatus != 0:
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

    supplier, registration = get_covered_supplier(doc, doc.bill_date or doc.posting_date)
    if not registration:
        return

    frappe.msgprint(
        _(
            "{0} is a {1} enterprise. Section 15 of the MSMED Act requires payment within {2} days, by {3}; this bill is due on {4}."
        ).format(
            bold(supplier),
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
            "args": {"doctype": doc.doctype, "name": doc.name, "due_date": str(limit)},
        },
    )


def validate_msme_order_terms(doc, method=None):
    if doc.docstatus != 0 or not (
        doc.is_new()
        or doc.has_value_changed("transaction_date")
        or doc.has_value_changed("supplier")
        or doc.has_value_changed("payment_terms_template")
    ):
        return

    due_dates = [getdate(row.due_date) for row in doc.get("payment_schedule") or [] if row.due_date]
    if not due_dates:
        return

    order_date = getdate(doc.transaction_date)
    last_due_date = max(due_dates)
    if last_due_date <= add_days(order_date, MSME_PAYMENT_DAYS):
        return

    supplier, registration = get_covered_supplier(doc, order_date)
    if not registration:
        return

    frappe.msgprint(
        _(
            "{0} is a {1} enterprise. This order's payment terms run {2} days from the order date; Section 15 of the MSMED Act allows at most {3} days from acceptance."
        ).format(
            bold(supplier),
            registration.enterprise_type,
            date_diff(last_due_date, order_date),
            MSME_PAYMENT_DAYS,
        ),
        title=_("MSME Payment Terms"),
        indicator="orange",
    )


def get_covered_supplier(doc, on_date):
    for supplier in get_bill_suppliers(doc):
        registration = get_supplier_msme_details(supplier, on_date)
        if is_msme_covered(registration):
            return supplier, registration

    return None, None
