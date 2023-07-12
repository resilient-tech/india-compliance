import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


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
