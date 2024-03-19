import click

import frappe

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import BOEGSTDetails
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.patches.post_install.improve_item_tax_template import (
    build_query_and_update_gst_details,
    compile_docs,
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
        docs = get_docs_to_update(doctype, gst_accounts)

        if not docs:
            continue

        update_gst_details(company, doctype, docs)


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


def update_gst_details(company, doctype, docs):
    chunk_size = 100
    total_docs = len(docs)

    with click.progressbar(
        range(0, total_docs, chunk_size),
        label=f"Updating {total_docs} {doctype}s",
    ) as bar:
        for index in bar:
            chunk = docs[index : index + chunk_size]

            taxes = get_taxes_for_docs(chunk, doctype)
            items = get_items_for_docs(chunk, doctype)
            complied_docs = compile_docs(taxes, items, doctype=doctype)

            if not complied_docs:
                continue

            gst_details = BOEGSTDetails().get(complied_docs.values(), doctype, company)

            if not gst_details:
                continue

            build_query_and_update_gst_details(gst_details, doctype)
            frappe.db.commit()


def get_taxes_for_docs(docs, doctype):
    taxes_doctype = "Bill of Entry Taxes"
    taxes = frappe.qb.DocType(taxes_doctype)
    return (
        frappe.qb.from_(taxes)
        .select(
            taxes.tax_amount,
            taxes.account_head,
            taxes.parent,
            taxes.item_wise_tax_rates,
        )
        .where(taxes.parenttype == doctype)
        .where(taxes.parent.isin(docs))
        .run(as_dict=True)
    )


def get_items_for_docs(docs, doctype):
    item_doctype = f"{doctype} Item"
    item = frappe.qb.DocType(item_doctype)

    query = (
        frappe.qb.from_(item)
        .select(
            item.name,
            item.parent,
            item.item_code,
            item.item_name,
            item.taxable_value,
        )
        .where(item.parenttype == doctype)
        .where(item.parent.isin(docs))
    )

    return query.run(as_dict=True)
