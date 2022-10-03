import frappe
from frappe import _
from frappe.utils import rounded

from india_compliance.gst_india.overrides.transaction import (
    get_valid_accounts,
    is_indian_registered_company,
)


def validate(doc, method=None):
    if not is_indian_registered_company(doc):
        return

    validate_zero_tax_options(doc)
    validate_tax_rates(doc)


def validate_zero_tax_options(doc):
    if not (doc.is_nil_rated or doc.is_exempted or doc.is_non_gst):
        return

    if doc.is_nil_rated + doc.is_exempted + doc.is_non_gst > 1:
        frappe.throw(
            _("Only one of Nil Rated, Exempted and Non GST can be selected at a time"),
            title="Invalid Options Selected",
        )

    if doc.tax_rate != 0:
        frappe.throw(
            _("Tax Rate should be 0 for Nil Rated / Exempted / Non GST template"),
            title="Invalid Tax Rate",
        )


def validate_tax_rates(doc):
    if doc.tax_rate < 0 or doc.tax_rate > 100:
        frappe.throw(
            _("Tax Rate should be between 0 and 100"), title="Invalid Tax Rate"
        )

    if not doc.taxes:
        return

    valid_accounts = get_valid_accounts(doc.company, for_sales=True, for_purchase=True)
    invalid_tax_rates = {}
    for row in doc.taxes:
        # check intra state
        if row.tax_type in valid_accounts[1] and doc.tax_rate != row.tax_rate * 2:
            invalid_tax_rates[row.idx] = doc.tax_rate / 2

        # check inter state
        elif row.tax_type in valid_accounts[2] and doc.tax_rate != row.tax_rate:
            invalid_tax_rates[row.idx] = doc.tax_rate

    if not invalid_tax_rates:
        return

    # throw
    message = "Plese make sure account taxes are in sync with tax rate mentioned."
    " Following rows have inconsistant tax rates: <br><br>"

    for idx, tax_rate in invalid_tax_rates.items():
        message += f"Row #{idx} - {rounded(tax_rate, 2)} <br>"

    frappe.throw(_(message), title="Invalid Tax Rates"),
