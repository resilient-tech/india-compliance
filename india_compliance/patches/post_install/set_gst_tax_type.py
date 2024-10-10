import frappe
from frappe.query_builder import Case

from india_compliance.gst_india.utils import get_gst_account_gst_tax_type_map

TAX_DOCTYPES = [
    "Sales Taxes and Charges",
    "Purchase Taxes and Charges",
    "Advance Taxes and Charges",
]


def execute():
    gst_account_tax_type_map = get_gst_account_gst_tax_type_map()

    if not gst_account_tax_type_map:
        return

    gst_accounts_by_tax_type = {}
    for account, tax_type in gst_account_tax_type_map.items():
        gst_accounts_by_tax_type.setdefault(tax_type, []).append(account)

    for tax_doctype in TAX_DOCTYPES:
        update_documents(tax_doctype, gst_accounts_by_tax_type)


def update_documents(taxes_doctype, gst_accounts_by_tax_type):
    taxes_doctype = frappe.qb.DocType(taxes_doctype)

    update_query = frappe.qb.update(taxes_doctype).where(
        taxes_doctype.parenttype.notin(
            ["Sales Taxes and Charges Template", "Purchase Taxes and Charges Template"]
        )
    )

    conditions = Case()

    for gst_tax_account, gst_tax_name in gst_accounts_by_tax_type.items():
        conditions = conditions.when(
            taxes_doctype.account_head.isin(gst_tax_name), gst_tax_account
        )

    conditions = conditions.else_(None)

    update_query.set(taxes_doctype.gst_tax_type, conditions).run()
