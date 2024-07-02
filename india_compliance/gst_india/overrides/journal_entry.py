import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import get_all_gst_accounts
from india_compliance.gst_india.utils.__init__ import get_gst_account_gst_tax_type_map


def before_validate(doc, method=None):
    if not doc.accounts:
        return

    gst_tax_account_map = get_gst_account_gst_tax_type_map()

    for tax in doc.accounts:
        # Setting as None if not GST Account
        tax.gst_tax_type = gst_tax_account_map.get(tax.account)


def validate(doc, method=None):
    if doc.company_gstin or not is_indian_registered_company(doc):
        return

    # validate company_gstin
    contains_gst_account = False
    gst_accounts = get_all_gst_accounts(doc.company)
    for row in doc.accounts:
        if row.account in gst_accounts:
            contains_gst_account = True
            break

    if contains_gst_account:
        frappe.throw(_("Company GSTIN is mandatory if any GST account is present."))
