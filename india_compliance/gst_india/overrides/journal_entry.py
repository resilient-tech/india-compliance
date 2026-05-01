import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import get_gst_account_gst_tax_type_map, get_gstin_list


def set_gst_tax_type(doc, method=None):
    if not doc.accounts:
        return

    gst_tax_account_map = get_gst_account_gst_tax_type_map()
    if not gst_tax_account_map:
        return

    for tax in doc.accounts:
        # Setting as None if not GST Account
        tax.gst_tax_type = gst_tax_account_map.get(tax.account)


def validate(doc, method=None):
    if not is_indian_registered_company(doc):
        return

    set_gst_tax_type(doc)

    if not doc.company_gstin and has_gst_accounts(doc):
        set_or_validate_company_gstin(doc)


def set_or_validate_company_gstin(doc):
    gstin_list = get_gstin_list(doc.company)

    if len(gstin_list) == 1:
        doc.company_gstin = gstin_list[0]
    else:
        frappe.throw(_("Company GSTIN is mandatory if any GST account is present."))


def has_gst_accounts(doc):
    return any(row.gst_tax_type for row in doc.accounts)
