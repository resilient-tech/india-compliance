import frappe

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


def validate(doc, method=None):
    if doc.company_gstin or not is_indian_registered_company(doc):
        return

    gst_accounts = get_all_gst_accounts(doc.company)
    if doc.account not in gst_accounts:
        return

    frappe.throw("Company GSTIN is a mandatory field for accounting of GST Accounts.")


def update_gl_dict(doc, gl_dict):
    if doc.company_gstin:
        gl_dict["company_gstin"] = doc.company_gstin
