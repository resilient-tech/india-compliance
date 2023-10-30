import click

import frappe

from india_compliance.gst_india.utils import get_all_gst_accounts, get_gstin_list

##############################################################################################################################
# Steps to manually migrate:
##############################################################################################################################
# Method 1:
# 1. Update company gstin for DocTypes where its Missing.
# 2. Execute the patch once again from GST Settings.
##############################################################################################################################
# Method 2 (Where Method 1 is not possible):
# 1. Update same company gstin for all DocTypes where its Missing.
# 2. Execute the patch once again from GST Settings.
# 3. Create adjustment Journal Entry to distribute the balance between other company gstins.
##############################################################################################################################


def execute():
    company_list = get_indian_companies()
    all_gst_accounts = get_gst_accounts(company_list)

    for company in company_list:
        update_gstin_for_je(company.name, all_gst_accounts)

    update_gl_entries(all_gst_accounts)
    voucher_types = verify_gstin_update(all_gst_accounts)
    return voucher_types


def get_indian_companies():
    return frappe.get_all("Company", filters={"country": "India"})


def get_gst_accounts(company_list=None):
    if not company_list:
        company_list = get_indian_companies()

    all_gst_accounts = []
    for company in company_list:
        gst_accounts = get_all_gst_accounts(company.name)
        all_gst_accounts.extend(gst_accounts)

    return all_gst_accounts


def verify_gstin_update(gst_accounts=None):
    if not gst_accounts:
        gst_accounts = get_gst_accounts()

    voucher_types = get_pending_voucher_types(gst_accounts)

    if voucher_types:
        toggle_allow_on_submit(True, voucher_types)
        return voucher_types

    toggle_allow_on_submit(False)


def update_gstin_for_je(company, gst_accounts):
    docs_with_gst_account = frappe.get_all(
        "Journal Entry",
        filters={
            "company": company,
            "docstatus": 1,
            "account": ("in", gst_accounts),
            "company_gstin": ("is", "not set"),
        },
        pluck="name",
    )

    if not docs_with_gst_account:
        return

    company_gstins = get_gstin_list(company)
    if not company_gstins:
        return

    if len(company_gstins) > 1:
        click.secho(
            "Multiple GSTINs found for company {0}. Please update Company GSTIN in Journal Entry manually to use GST Balance Report.".format(
                company
            ),
            fg="yellow",
        )

    journal_entries = [docname for docname in docs_with_gst_account]
    return _update_gstins_for_je(journal_entries, company_gstins[0])


def _update_gstins_for_je(je_list, gstin):
    doc = frappe.qb.DocType("Journal Entry")
    frappe.qb.update(doc).set(doc.company_gstin, gstin).where(
        doc.name.isin(je_list)
    ).run()


def update_gl_entries(gst_accounts):
    voucher_types = get_pending_voucher_types(gst_accounts)

    if not voucher_types:
        return

    error_voucher_types = set()
    for voucher_type in voucher_types:
        while True:
            entries = fetch_gl_entries(gst_accounts, voucher_type, error_voucher_types)
            if not entries:
                break

            gstin_voucher_map = get_gstin_wise_vouchers(entries)
            _update_gl_entries(gstin_voucher_map)

            # nosemgrep
            frappe.db.commit()  # commit after every 50000 entries

    if error_voucher_types:
        click.secho(
            "Company GSTIN is now a required field in GL Entry with GST Account. Seems it is missing in your custom doctypes: {0}".format(
                ", ".join(error_voucher_types)
            ),
            fg="red",
        )


def fetch_gl_entries(gst_accounts, voucher_type, error_voucher_types):
    doc = frappe.qb.DocType(voucher_type)
    gl_doc = frappe.qb.DocType("GL Entry")

    try:
        return (
            frappe.qb.from_(gl_doc)
            .join(doc)
            .on((gl_doc.voucher_no == doc.name) & (gl_doc.voucher_type == voucher_type))
            .where(gl_doc.account.isin(gst_accounts))
            .where(gl_doc.company_gstin.isnull() | (gl_doc.company_gstin == ""))
            .where(doc.company_gstin.notnull() & (doc.company_gstin != ""))
            .select(gl_doc.name, doc.company_gstin)
            .limit(100000)
            .run(as_dict=True)
        )
    except Exception:
        error_voucher_types.add(voucher_type)


def get_gstin_wise_vouchers(entries):
    gstin_voucher_map = frappe._dict()
    for entry in entries:
        gstin_voucher_map.setdefault(entry.company_gstin, []).append(entry.name)

    return gstin_voucher_map


def _update_gl_entries(gstin_voucher_map):
    gl_entry = frappe.qb.DocType("GL Entry")
    for gstin, gl_entries in gstin_voucher_map.items():
        frappe.qb.update(gl_entry).set(gl_entry.company_gstin, gstin).where(
            gl_entry.name.isin(gl_entries)
        ).run()


def get_pending_voucher_types(gst_accounts):
    return frappe.get_all(
        "GL Entry",
        filters={
            "account": ("in", gst_accounts),
            "company_gstin": ("is", "not set"),
            "is_cancelled": 0,
        },
        pluck="voucher_type",
        distinct=True,
    )


def toggle_allow_on_submit(allow=True, voucher_types=None):
    custom_field = frappe.qb.DocType("Custom Field")
    query = (
        frappe.qb.update(custom_field)
        .set(custom_field.allow_on_submit, bool(allow))
        .where(custom_field.fieldname == "company_gstin")
    )

    if voucher_types:
        query = query.where(custom_field.dt.isin(voucher_types))

    query.run()
