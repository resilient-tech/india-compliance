import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.report.gst_balance.gst_balance import (
    get_pending_voucher_types,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


def validate(doc, method=None):
    if doc.company_gstin or not is_indian_registered_company(doc):
        return

    gst_accounts = get_all_gst_accounts(doc.company)
    if doc.account not in gst_accounts:
        return

    msg = _("Company GSTIN is a mandatory field for accounting of GST Accounts.")
    if get_pending_voucher_types(doc.company)[0]:
        # on older transaction where the patch hasn't run succesfully
        msg += " "
        msg += _(
            "Run Update GSTIN patch from GST Balance report to update GSTIN in all transactions."
        )

    frappe.throw(msg)


def update_gl_dict_with_regional_fields(doc, gl_dict):
    if doc.get("company_gstin"):
        gl_dict["company_gstin"] = doc.company_gstin
