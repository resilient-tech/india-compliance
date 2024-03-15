import frappe

from india_compliance.gst_india.constants import SALES_DOCTYPES
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.patches.post_install.improve_item_tax_template import (
    _update_gst_details,
)


def execute():
    companies = get_indian_companies()
    update_gst_details_for_transactions(companies)


def get_indian_companies():
    return frappe.get_all("Company", filters={"country": ("India")}, pluck="name")


def update_gst_details_for_transactions(companies):
    for company in companies:
        gst_accounts = []
        gst_accounts.extend(
            filter(
                None,
                get_gst_accounts_by_type(
                    company, account_type="Input", throw=False
                ).values(),
            )
        )

        if not gst_accounts:
            continue

        doctype = "Bill of Entry"
        is_sales_doctype = doctype in SALES_DOCTYPES
        docs = get_docs_to_update(doctype, gst_accounts)

        if not docs:
            continue

        _update_gst_details(company, doctype, is_sales_doctype, docs)


def get_docs_to_update(doctype, gst_accounts):
    gl_entry = frappe.qb.DocType("GL Entry")

    return (
        frappe.qb.from_(gl_entry)
        .select(gl_entry.voucher_no)
        .where(gl_entry.voucher_type == doctype)
        .where(gl_entry.account.isin(gst_accounts))
        .where(gl_entry.is_cancelled == 0)
        .distinct()
        .run(pluck=True)
    )
