import frappe
from frappe import _

from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_invalid_gst_accounts,
)


def validate(doc, method=None):
    """
    Period Closing Voucher closes all Income and Expense Accounts, and such closing
    entries have no Company GSTIN. Validate GST Accounts before closing the period.
    """
    if not is_indian_registered_company(doc):
        return

    invalid_accounts = get_invalid_gst_accounts(get_all_gst_accounts(doc.company))
    if not invalid_accounts:
        return

    account_links = "".join(f"<li>{frappe.bold(account)}</li>" for account in invalid_accounts)

    msg = _("Root Type of following GST Accounts should be Asset or Liability:")
    msg += f"<br><br><ul>{account_links}</ul>"

    frappe.throw(msg)
