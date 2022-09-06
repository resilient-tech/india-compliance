import click

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from india_compliance.gst_india.utils import (
    delete_old_fields,
    get_all_gst_accounts,
    get_gstin_list,
)

##############################################################################################################################
# Assumptions for Multi GSTIN Setup:
# 1. Company used to maintain separate GST Accounts for each GSTIN.
# 2. Journal Entries for multiple GST Accounts were not clubbed.
##############################################################################################################################

##############################################################################################################################
# Steps to manually migrate to new setup:
##############################################################################################################################
# Method 1:
# 1. Update company gstin for Journal Entries where not handled by Patch.
# 2. Execute the patch once again from GST Settings.
##############################################################################################################################
# Method 2 (Where Method 1 is not possible):
# 1. Book all Journal Entries for one company gstin.
# 2. Create adjustment Journal Entry to distribute the balance between other company gstins.
##############################################################################################################################

CUSTOM_FIELDS = {
    ("Journal Entry", "GL Entry"): [
        {
            "fieldname": "company_gstin",
            "label": "Company GSTIN",
            "fieldtype": "Autocomplete",
            "insert_after": "company",
            "hidden": 0,
            "read_only": 0,
            "print_hide": 1,
            "fetch_from": "",
            "depends_on": "",
            "mandatory_depends_on": "",
            "translatable": 0,
        }
    ]
}


def execute():
    if not frappe.flags.in_install:
        create_custom_fields(CUSTOM_FIELDS)
        delete_old_fields("company_address", "Journal Entry")

    company_list = frappe.get_all("Company", filters={"country": "India"})
    all_gst_accounts = []
    for company in company_list:
        gst_accounts = get_all_gst_accounts(company.name)
        update_gstin_for_je(company.name, gst_accounts)
        all_gst_accounts.extend(gst_accounts)

    update_gl_entries(all_gst_accounts)


def update_gstin_for_je(company, gst_accounts):
    docs_with_gst_account = frappe.get_all(
        "Journal Entry",
        filters={
            "company": company,
            "docstatus": 1,
            "account": ("in", gst_accounts),
            "company_gstin": ("is", "not set"),
        },
        fields=["name", "`tabJournal Entry Account`.account"],
    )

    if not docs_with_gst_account:
        return

    company_gstins = get_gstin_list(company)
    if len(company_gstins) == 1:
        journal_entries = [doc.name for doc in docs_with_gst_account]
        return _update_gstins_for_je(journal_entries, company_gstins[0])

    # Multi GSTIN Setup
    account_gstin_map = frappe._dict()
    for doc in docs_with_gst_account:
        if doc.account not in account_gstin_map:
            account_gstin_map[doc.account] = get_related_company_gstin(doc.account)

    for gstin in set(account_gstin_map.values()):
        if not gstin:
            gstin = company_gstins[0]

        journal_entries = [
            doc.name
            for doc in docs_with_gst_account
            if account_gstin_map[doc.account] == gstin
        ]
        _update_gstins_for_je(journal_entries, gstin)

    click.secho(
        "We have updated your Journal Entries with Company GSTIN. Kindly refer to the Documentation for Multi GSTIN Setup and make appropriate changes if needed.",
        fg="yellow",
    )


def _update_gstins_for_je(je_list, gstin):
    doc = frappe.qb.DocType("Journal Entry")
    for chunk in chunks(je_list):
        frappe.qb.update(doc).set(doc.company_gstin, gstin).where(
            doc.name.isin(chunk)
        ).run()


def get_related_company_gstin(account):
    for doctype in ("Purchase Invoice", "Sales Invoice", "Payment Entry"):
        company_gstin = frappe.get_all(
            doctype,
            filters={"account_head": account, "docstatus": 1},
            pluck="company_gstin",
            limit=1,
        )

        if company_gstin:
            return company_gstin


def update_gl_entries(gst_accounts):
    voucher_types = frappe.get_all(
        "GL Entry",
        filters={"account": ["in", gst_accounts], "company_gstin": ("is", "not set")},
        pluck="voucher_type",
        group_by="voucher_type",
    )

    error_voucher_types = set()
    gl_entries = []
    for voucher_type in voucher_types:
        doc = frappe.qb.DocType(voucher_type)
        gl_doc = frappe.qb.DocType("GL Entry")
        try:
            gl_entries.extend(
                frappe.qb.from_(gl_doc)
                .join(doc)
                .on(
                    (gl_doc.voucher_no == doc.name)
                    & (gl_doc.voucher_type == voucher_type)
                )
                .where(gl_doc.account.isin(gst_accounts))
                .select(gl_doc.name, doc.company_gstin, doc.company)
                .run(as_dict=True)
            )
        except Exception:
            error_voucher_types.add(voucher_type)

    gstin_voucher_map = frappe._dict()
    default_gstin = frappe._dict()
    for gl_entry in gl_entries:
        # handle cases where company_gstin is not set in standard doctypes like Sales Invoice
        if not gl_entry.company_gstin:
            if gl_entry.company not in default_gstin:
                default_gstin[gl_entry.company] = get_gstin_list(gl_entry.company)[0]

            gl_entry.company_gstin = default_gstin[gl_entry.company]
        gstin_voucher_map.setdefault(gl_entry.company_gstin, []).append(gl_entry.name)

    for company_gstin, gl_entry_list in gstin_voucher_map.items():
        doc = frappe.qb.DocType("GL Entry")
        for chunk in chunks(gl_entry_list):
            frappe.qb.update(doc).set(doc.company_gstin, company_gstin).where(
                doc.name.isin(chunk)
            ).run()

    if error_voucher_types:
        click.secho(
            "Company GSTIN is now a required field in GL Entry with GST Account. Seems it is missing in your custom doctypes: {0}".format(
                ", ".join(error_voucher_types)
            ),
            fg="red",
        )


def chunks(list, n=2000):
    """Returns a chunks of size n. Commiting in smaller chunks to avoid timeout"""

    for i in range(0, len(list), n):
        yield list[i : i + n]
        frappe.db.commit()
