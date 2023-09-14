import frappe
from frappe.utils import cstr, flt, getdate
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.accounts.utils import create_payment_ledger_entry

from india_compliance.gst_india.utils import get_all_gst_accounts


def validate(doc, method=None):
    # GST taxes should only be necessary when receiving amount. Not when paying.
    # Address, GSTIN, POS, Taxes validation if taxes are collected.
    # Only allow GST accounts in taxes?
    pass


def update_place_of_supply(doc, method):
    country = frappe.get_cached_value("Company", doc.company, "country")
    if country != "India":
        return

    address = frappe.db.get_value(
        "Address",
        doc.get("customer_address"),
        ["gst_state", "gst_state_number"],
        as_dict=1,
    )
    if address and address.gst_state and address.gst_state_number:
        doc.place_of_supply = (
            cstr(address.gst_state_number) + "-" + cstr(address.gst_state)
        )


def make_gst_revesal_entry_from_advance_payment(doc, method=None):
    """
    This functionality aims to create a GST reversal entry where GST was paid in advance

    On Submit: Creates GLEs and PLEs for all references.
    On Update after Submit: Creates GLEs for new references. Creates PLEs for all references.
    """
    gl_dict = []

    if not doc.taxes:
        return

    for row in doc.get("references"):
        gl_dict.extend(get_gl_for_advance_gst_reversal(doc, row))

    if not gl_dict:
        return

    # Creates GLEs and PLEs
    make_gl_entries(gl_dict)


def get_gl_for_advance_gst_reversal(payment_entry, reference_row):
    voucher_date = frappe.db.get_value(
        reference_row.reference_doctype, reference_row.reference_name, "posting_date"
    )
    posting_date = (
        payment_entry.posting_date
        if getdate(payment_entry.posting_date) > getdate(voucher_date)
        else voucher_date
    )

    taxes = get_proportionate_taxes_for_reversal(payment_entry, reference_row)

    if not taxes:
        return

    total_amount = sum(taxes.values())

    gl_dicts = []
    args = {
        "posting_date": posting_date,
        "party_type": payment_entry.party_type,
        "party": payment_entry.party,
        "voucher_detail_no": reference_row.name,
        "remarks": f"Reversal for GST on Advance Payment Entry"
        f" {payment_entry.name} against {reference_row.reference_doctype} {reference_row.reference_name}",
    }

    # Reduce receivables
    gl_entry = payment_entry.get_gl_dict(
        {
            "account": reference_row.account,
            "credit": total_amount,
            "credit_in_account_currency": total_amount,
            "against_voucher_type": reference_row.reference_doctype,
            "against_voucher": reference_row.reference_name,
            **args,
        },
        item=reference_row,
    )

    if frappe.db.exists("GL Entry", args):
        # All existing PLE are delinked and new ones are created everytime on update
        # refer: reconcile_against_document in utils.py
        create_payment_ledger_entry(
            [gl_entry], update_outstanding="No", cancel=0, adv_adj=1
        )

        return gl_dicts

    gl_dicts.append(gl_entry)

    # Reverse taxes
    for account, amount in taxes.items():
        gl_dicts.append(
            payment_entry.get_gl_dict(
                {
                    "account": account,
                    "debit": amount,
                    "debit_in_account_currency": amount,
                    "against_voucher_type": payment_entry.doctype,
                    "against_voucher": payment_entry.name,
                    **args,
                },
                item=reference_row,
            )
        )

    return gl_dicts


def get_proportionate_taxes_for_reversal(payment_entry, reference_row):
    """
    This function calculates proportionate taxes for reversal of GST paid in advance
    """
    gst_accounts = get_all_gst_accounts(payment_entry.company)
    taxes = {
        row.account_head: row.base_tax_amount
        for row in payment_entry.taxes
        if row.account_head in gst_accounts
    }

    if not taxes:
        return

    # Ensure there is no rounding error
    if (
        not payment_entry.unallocated_amount
        and payment_entry.references[-1].idx == reference_row.idx
    ):
        return balance_taxes(payment_entry, reference_row, taxes)

    return get_proportionate_taxes_for_row(payment_entry, reference_row, taxes)


def get_proportionate_taxes_for_row(payment_entry, reference_row, taxes):
    base_allocated_amount = payment_entry.calculate_base_allocated_amount_for_reference(
        reference_row
    )
    for account, amount in taxes.items():
        taxes[account] = flt(
            amount * base_allocated_amount / payment_entry.base_paid_amount, 2
        )

    return taxes


def balance_taxes(payment_entry, reference_row, taxes):
    for account, amount in taxes.items():
        for allocation_row in payment_entry.references:
            if allocation_row.reference_name == reference_row.reference_name:
                continue

            taxes[account] = taxes[account] - flt(
                amount
                * payment_entry.calculate_base_allocated_amount_for_reference(
                    allocation_row
                )
                / payment_entry.base_paid_amount,
                2,
            )

    return taxes
