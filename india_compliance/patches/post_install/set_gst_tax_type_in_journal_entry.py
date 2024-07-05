import frappe
from frappe.query_builder import Case

from india_compliance.gst_india.utils import get_gst_account_gst_tax_type_map


def execute():
    gst_account_tax_type_map = get_gst_account_gst_tax_type_map()
    if not gst_account_tax_type_map:
        return

    gst_accounts_by_tax_type = {}
    for account, tax_type in gst_account_tax_type_map.items():
        gst_accounts_by_tax_type.setdefault(tax_type, []).append(account)

    taxes_doctype = frappe.qb.DocType("Journal Entry Account")

    update_query = frappe.qb.update(taxes_doctype)
    conditions = Case()

    for gst_tax_account, gst_tax_name in gst_accounts_by_tax_type.items():
        conditions = conditions.when(
            taxes_doctype.account.isin(gst_tax_name), gst_tax_account
        )
    conditions = conditions.else_(None)
    update_query.set(taxes_doctype.gst_tax_type, conditions).run()
