import frappe
from frappe.query_builder import Case

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS

TAX_DOCTYPES = [
    "Sales Taxes and Charges",
    "Purchase Taxes and Charges",
    "Advance Taxes and Charges",
    "Bill of Entry Taxes",
]


def execute():
    gst_accounts = frappe.get_doc("GST Settings").gst_accounts
    gst_details = {}

    for row in gst_accounts:
        for account in GST_ACCOUNT_FIELDS:
            account_value = row.get(account)

            if not account_value:
                continue

            account_key = account[:-8]
            if "Reverse Charge" in row.get("account_type"):
                account_key = account_key + "_rcm"

            gst_details.setdefault(account_key, []).append(account_value)

    if not gst_details:
        return

    for tax_doctype in TAX_DOCTYPES:
        update_documents(tax_doctype, gst_details)


def update_documents(taxes_doctype, gst_accounts):
    taxes_doctype = frappe.qb.DocType(taxes_doctype)

    update_query = frappe.qb.update(taxes_doctype).where(
        taxes_doctype.parenttype.notin(
            ["Sales Taxes and Charges Template", "Purchase Taxes and Charges Template"]
        )
    )

    conditions = Case()

    for gst_tax_account, gst_tax_name in gst_accounts.items():
        conditions = conditions.when(
            taxes_doctype.account_head.isin(gst_tax_name), gst_tax_account
        )

    conditions = conditions.else_(None)

    update_query.set(taxes_doctype.gst_tax_type, conditions).run()
