import frappe
from frappe import _
from frappe.utils import rounded

from india_compliance.gst_india.overrides.transaction import get_valid_accounts


def validate(doc, method=None):
    validate_zero_tax_options(doc)
    validate_tax_rates(doc)


def validate_zero_tax_options(doc):
    if doc.gst_treatment != "Taxable":
        doc.gst_rate = 0
        return

    if doc.gst_rate == 0:
        frappe.throw(
            _("GST Rate cannot be zero for <strong>Taxable</strong> GST Treatment"),
            title=_("Invalid GST Rate"),
        )


def validate_tax_rates(doc):
    if doc.gst_rate < 0 or doc.gst_rate > 100:
        frappe.throw(
            _("GST Rate should be between 0 and 100"), title=_("Invalid GST Rate")
        )

    if not doc.taxes:
        return

    __, intra_state_accounts, inter_state_accounts = get_valid_accounts(
        doc.company, for_sales=True, for_purchase=True, throw=False
    )

    if not intra_state_accounts and not inter_state_accounts:
        return

    invalid_tax_rates = {}
    for row in doc.taxes:
        # check intra state
        if row.tax_type in intra_state_accounts and doc.gst_rate != row.tax_rate * 2:
            invalid_tax_rates[row.idx] = doc.gst_rate / 2

        # check inter state
        elif row.tax_type in inter_state_accounts and doc.gst_rate != row.tax_rate:
            invalid_tax_rates[row.idx] = doc.gst_rate

    if not invalid_tax_rates:
        return

    # throw
    message = (
        "Plese make sure account tax rates are in sync with GST rate mentioned."
        " Following rows have inconsistant tax rates: <br><br>"
    )

    for idx, tax_rate in invalid_tax_rates.items():
        message += f"Row #{idx} - should be {rounded(tax_rate, 2)}% <br>"

    frappe.throw(_(message), title=_("Invalid Tax Rates"))
