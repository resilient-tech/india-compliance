import frappe
from frappe import _
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.constants import ITC_VOUCHER_TYPES
from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
)
from india_compliance.gst_india.utils import get_gst_account_gst_tax_type_map, get_gstin_list


def is_link_used_as_reference_only(doc, row):
    return (
        doc.voucher_type in ITC_VOUCHER_TYPES
        and row.reference_type == "Purchase Invoice"
        and not row.party_type
        and is_indian_registered_company(doc)
    )


def set_gst_tax_type(doc, method=None):
    if not doc.accounts:
        return

    gst_tax_account_map = get_gst_account_gst_tax_type_map()
    if not gst_tax_account_map:
        return

    for tax in doc.accounts:
        # Setting as None if not GST Account
        tax.gst_tax_type = gst_tax_account_map.get(tax.account)


def validate(doc, method=None):
    if not is_indian_registered_company(doc):
        return

    set_gst_tax_type(doc)

    if not doc.company_gstin and has_gst_accounts(doc):
        set_or_validate_company_gstin(doc)

    validate_invoices_linked_for_itc(doc)


def set_or_validate_company_gstin(doc):
    gstin_list = get_gstin_list(doc.company)

    if len(gstin_list) == 1:
        doc.company_gstin = gstin_list[0]
    else:
        frappe.throw(_("Company GSTIN is mandatory if any GST account is present."))


def has_gst_accounts(doc):
    return any(row.gst_tax_type for row in doc.accounts)


def validate_invoices_linked_for_itc(doc):
    invoice_link_rows = [row for row in doc.accounts if is_link_used_as_reference_only(doc, row)]
    if not invoice_link_rows:
        return

    linked_invoices = {
        invoice.name: invoice
        for invoice in frappe.get_all(
            "Purchase Invoice",
            filters={"name": ("in", {row.reference_name for row in invoice_link_rows})},
            fields=["name", "docstatus", "company", "company_gstin"],
        )
    }

    for row in invoice_link_rows:
        invoice = linked_invoices.get(row.reference_name)
        if not invoice or invoice.docstatus != 1:
            frappe.throw(
                _("Row #{0}: Purchase Invoice {1} is not submitted").format(row.idx, row.reference_name)
            )

        if invoice.company != doc.company:
            frappe.throw(
                _("Row #{0}: Purchase Invoice {1} belongs to Company {2}").format(
                    row.idx, row.reference_name, invoice.company
                )
            )

        if invoice.company_gstin != doc.company_gstin:
            frappe.throw(
                _("Row #{0}: Purchase Invoice {1} belongs to Company GSTIN {2}").format(
                    row.idx, row.reference_name, invoice.company_gstin
                )
            )


def prevent_cancel_of_invoice_linked_in_itc_entry(doc, method=None):
    journal_entry = frappe.qb.DocType("Journal Entry")
    journal_entry_account = frappe.qb.DocType("Journal Entry Account")

    linked_itc_entries = (
        frappe.qb.from_(journal_entry_account)
        .join(journal_entry)
        .on(journal_entry.name == journal_entry_account.parent)
        .select(journal_entry.name)
        .distinct()
        .where(journal_entry.docstatus == 1)
        .where(journal_entry.voucher_type.isin(ITC_VOUCHER_TYPES))
        .where(journal_entry_account.reference_type == doc.doctype)
        .where(journal_entry_account.reference_name == doc.name)
        .where(IfNull(journal_entry_account.party_type, "") == "")
        .run(pluck=True)
    )

    if linked_itc_entries:
        frappe.throw(
            _("Cancel ITC Journal Entry {0} before cancelling {1}").format(
                ", ".join(linked_itc_entries), doc.name
            ),
            title=_("Linked ITC Journal Entry"),
        )
