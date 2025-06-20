import frappe
from frappe import _
from frappe.utils import flt, rounded

from india_compliance.gst_india.overrides.transaction import get_valid_accounts
from india_compliance.gst_india.utils import get_gst_accounts_by_type


def validate(doc, method=None):
    doc.gst_rate = flt(doc.gst_rate)
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
        tax_rate = abs(row.get("tax_rate") or 0)

        # check intra state
        if row.tax_type in intra_state_accounts and doc.gst_rate != tax_rate * 2:
            invalid_tax_rates[row.idx] = doc.gst_rate / 2

        # check inter state
        elif row.tax_type in inter_state_accounts and doc.gst_rate != tax_rate:
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


@frappe.whitelist()
def get_valid_gst_accounts(company):
    frappe.has_permission("Item Tax Template", "read", throw=True)

    return [
        *get_valid_accounts(company, for_sales=True, for_purchase=True, throw=False),
        get_accounts_with_negative_rate(company),
    ]


def get_accounts_with_negative_rate(company):
    """
    - Include all Sales RCM accounts
    - Include all Purchase RCM accounts based on how taxes and charges template is created
    """
    negative_rate_accounts = list(
        get_gst_accounts_by_type(company, "Sales Reverse Charge", throw=False).values()
    )
    negative_rate_accounts += list(
        get_gst_accounts_by_type(company, "Output Refund", throw=False).values()
    )  # add refund accounts

    purchase_rcm_accounts = list(
        get_gst_accounts_by_type(
            company, "Purchase Reverse Charge", throw=False
        ).values()
    )

    if not purchase_rcm_accounts:
        return negative_rate_accounts

    add_deduct_tax = frappe.get_value(
        "Purchase Taxes and Charges",
        {
            "parenttype": "Purchase Taxes and Charges Template",
            "account_head": ["in", purchase_rcm_accounts],
        },
        "add_deduct_tax",
    )

    if add_deduct_tax == "Add":
        negative_rate_accounts += purchase_rcm_accounts

    return negative_rate_accounts
