import frappe
from frappe.query_builder.functions import Count

from india_compliance.gst_india.constants import SALES_DOCTYPES
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.patches.post_install.improve_item_tax_template import (
    _update_gst_details,
)


def execute():
    companies = get_indian_companies()
    update_gst_details_for_transactions(companies)


def get_indian_companies():
    return frappe.get_all("Company", filters={"country": "India"}, pluck="name")


def update_gst_details_for_transactions(companies):
    for company in companies:
        gst_accounts = []
        for account_type in ["Input", "Output"]:
            gst_accounts.extend(
                get_gst_accounts_by_type(company, account_type, throw=False).values()
            )

        if not gst_accounts:
            continue

        for doctype in ("Sales Invoice", "Purchase Invoice"):
            is_sales_doctype = doctype in SALES_DOCTYPES
            docs = get_docs_with_gst_accounts_and_same_item_multiple_times(
                doctype, gst_accounts
            )
            if not docs:
                continue

            _update_gst_details(company, doctype, is_sales_doctype, docs)


def get_docs_with_gst_accounts_and_same_item_multiple_times(doctype, gst_accounts):
    item_doctype = frappe.qb.DocType(f"{doctype} Item")
    gl_entry = frappe.qb.DocType("GL Entry")

    invoices_with_same_item_multiple_times = (
        frappe.qb.from_(item_doctype)
        .select(item_doctype.parent)
        .groupby(item_doctype.parent, item_doctype.item_code)
        .having(Count((item_doctype.item_code)) > 2)
    )

    return (
        frappe.qb.from_(gl_entry)
        .select(gl_entry.voucher_no)
        .where(gl_entry.voucher_type == doctype)
        .where(gl_entry.account.isin(gst_accounts))
        .where(gl_entry.is_cancelled == 0)
        .where(gl_entry.voucher_no.isin(invoices_with_same_item_multiple_times))
        .distinct()
        .run(pluck=True)
    )
