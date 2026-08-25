import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


def validate(doc, method=None):
    """
    Validate that GST Accounts are not Income or Expense Accounts before closing the period.
    """
    if not is_indian_registered_company(doc):
        return

    gst_accounts = get_all_gst_accounts(doc.company)
    if not gst_accounts:
        return

    pl_gst_accounts = frappe.get_all(
        "Account",
        filters={"name": ("in", gst_accounts), "root_type": ("in", ("Income", "Expense"))},
        pluck="name",
    )

    if not pl_gst_accounts:
        return

    frappe.throw(
        pl_gst_accounts,
        title=_("GST Accounts cannot be Income or Expense Accounts"),
        as_list=True,
    )
