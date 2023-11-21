import frappe
from frappe import _

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

    frappe.throw(
        _(
            "Company GSTIN is a mandatory field for accounting of GST Accounts."
            " Run `Update GSTIN` patch from GST Balance Report to update GSTIN in all transactions."
        )
    )


def update_gl_dict_with_regional_fields(doc, gl_dict):
    if doc.get("company_gstin"):
        gl_dict["company_gstin"] = doc.company_gstin
