import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_default_address
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.accounts.utils import create_payment_ledger_entry
from erpnext.controllers.accounts_controller import get_advance_payment_entries

from india_compliance.gst_india.overrides.transaction import get_gst_details
from india_compliance.gst_india.overrides.transaction import (
    validate_transaction as validate_transaction_for_advance_payment,
)
from india_compliance.gst_india.utils import get_all_gst_accounts


@frappe.whitelist()
def get_outstanding_reference_documents(args, validate=False):
    from erpnext.accounts.doctype.payment_entry.payment_entry import (
        get_outstanding_reference_documents,
    )

    reference_documents = get_outstanding_reference_documents(args, validate)

    invoice_list = [
        item["voucher_no"]
        for item in reference_documents
        if item["voucher_type"] == "Purchase Invoice"
    ]
    if not invoice_list:
        return reference_documents

    reconciliation_status_dict = get_reconciliation_status_for_invoice_list(
        invoice_list
    )

    for d in reference_documents:
        d["reconciliation_status"] = reconciliation_status_dict.get(d["voucher_no"], "")

    return reference_documents


def get_reconciliation_status_for_invoice_list(invoice_list):
    if not invoice_list:
        return

    invoice_list = frappe.parse_json(invoice_list)

    reconciliation_status_dict = dict(
        frappe.get_all(
            "Purchase Invoice",
            filters={"name": ["in", invoice_list]},
            fields=("name", "reconciliation_status"),
            as_list=True,
        )
    )
    return reconciliation_status_dict


def onload(doc, method=None):
    if not doc.references:
        return

    invoice_list = [
        x.reference_name
        for x in doc.references
        if x.reference_doctype == "Purchase Invoice"
    ]

    reconciliation_status_dict = get_reconciliation_status_for_invoice_list(
        invoice_list
    )

    doc.set_onload("reconciliation_status_dict", reconciliation_status_dict)


def validate(doc, method=None):
    if not doc.taxes:
        return

    if doc.party_type == "Customer":
        # Presume is export with GST if GST accounts are present
        doc.is_export_with_gst = 1
        validate_transaction_for_advance_payment(doc, method)

    else:
        gst_accounts = get_all_gst_accounts(doc.company)
        for row in doc.taxes:
            if row.account_head in gst_accounts and row.tax_amount != 0:
                frappe.throw(
                    _("GST Taxes are not allowed for Supplier Advance Payment Entry")
                )


def on_submit(doc, method=None):
    make_gst_revesal_entry_from_advance_payment(doc)


def on_update_after_submit(doc, method=None):
    make_gst_revesal_entry_from_advance_payment(doc)


@frappe.whitelist()
def update_party_details(party_details, doctype, company):
    party_details = frappe.parse_json(party_details)

    address = get_default_address("Customer", party_details.get("customer"))
    party_details.update(customer_address=address)

    # update gst details
    if address:
        party_details.update(
            frappe.db.get_value(
                "Address",
                address,
                ["gstin as billing_address_gstin"],
                as_dict=1,
            )
        )

    # Update address for update
    response = {
        "customer_address": address,  # should be set first as gst_category and gstin is fetched from address
        **get_gst_details(party_details, doctype, company, update_place_of_supply=True),
    }

    return response


def make_gst_revesal_entry_from_advance_payment(doc):
    """
    This functionality aims to create a GST reversal entry where GST was paid in advance

    On Submit: Creates GLEs and PLEs for all references.
    On Update after Submit: Creates GLEs for new references. Creates PLEs for all references.
    """
    gl_dict = []
    update_gl_for_advance_gst_reversal(gl_dict, doc)

    if not gl_dict:
        return

    # Creates GLEs and PLEs
    make_gl_entries(gl_dict)


def update_gl_for_advance_gst_reversal(gl_dict, doc):
    if not doc.taxes:
        return

    for row in doc.get("references"):
        if row.reference_doctype not in ("Sales Invoice", "Journal Entry"):
            continue

        gl_dict.extend(_get_gl_for_advance_gst_reversal(doc, row))


def _get_gl_for_advance_gst_reversal(payment_entry, reference_row):
    gl_dicts = []
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
        return gl_dicts

    total_amount = sum(taxes.values())

    args = {
        "posting_date": posting_date,
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
            "party_type": payment_entry.party_type,
            "party": payment_entry.party,
            "against_voucher_type": reference_row.reference_doctype,
            "against_voucher": reference_row.reference_name,
            **args,
        },
        item=reference_row,
    )

    if frappe.db.exists("GL Entry", args):
        if frappe.db.exists("Payment Ledger Entry", {**args, "delinked": 0}):
            return gl_dicts

        # All existing PLE are delinked and new ones are created everytime on update
        # refer: reconcile_against_document in utils.py
        create_payment_ledger_entry(
            [gl_entry], update_outstanding="No", cancel=0, adv_adj=1
        )

        return gl_dicts

    if not frappe.flags.gst_excess_allocation_validated:
        total_allocation = total_amount + reference_row.allocated_amount
        excess_allocation = total_allocation - reference_row.outstanding_amount

        if excess_allocation > 1:
            frappe.throw(
                _(
                    "Outstanding amount {0} is less than the total allocated amount"
                    " with taxes {1} for {2} {3}"
                ).format(
                    reference_row.outstanding_amount,
                    total_allocation,
                    reference_row.reference_doctype,
                    reference_row.reference_name,
                )
            )

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
    # Compile taxes
    gst_accounts = get_all_gst_accounts(payment_entry.company)
    taxes = {}
    for row in payment_entry.taxes:
        if row.account_head not in gst_accounts:
            continue

        taxes.setdefault(row.account_head, 0)
        taxes[row.account_head] += row.base_tax_amount

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


def get_advance_payment_entries_for_regional(
    party_type,
    party,
    party_account,
    order_doctype,
    order_list=None,
    include_unallocated=True,
    against_all_orders=False,
    limit=None,
    condition=None,
):
    """
    Get Advance Payment Entries with GST Taxes
    """

    payment_entries = get_advance_payment_entries(
        party_type=party_type,
        party=party,
        party_account=party_account,
        order_doctype=order_doctype,
        order_list=order_list,
        include_unallocated=include_unallocated,
        against_all_orders=against_all_orders,
        limit=limit,
        condition=condition,
    )

    # if not Sales Invoice and is Payment Reconciliation
    if not condition or not payment_entries:
        return payment_entries

    company = frappe.db.get_value("Account", party_account, "company")
    taxes = get_taxes_summary(company, payment_entries)

    for pe in payment_entries:
        tax_row = taxes.get(
            pe.reference_name,
            frappe._dict(paid_amount=1, tax_amount=0, tax_amount_reversed=0),
        )
        pe.amount += tax_row.tax_amount - tax_row.tax_amount_reversed

    return payment_entries


def adjust_allocations_for_taxes_in_payment_reconciliation(doc):
    if not doc.allocation:
        return

    taxes = get_taxes_summary(doc.company, doc.allocation)
    taxes = {
        tax.payment_entry: frappe._dict(
            {
                **tax,
                "paid_proportion": tax.paid_amount / (tax.paid_amount + tax.tax_amount),
            }
        )
        for tax in taxes.values()
    }

    for row in doc.allocation:
        tax_row = taxes.get(row.reference_name)
        if not tax_row:
            continue

        row.update(
            {
                "amount": tax_row.unallocated_amount,
                "allocated_amount": flt(
                    row.get("allocated_amount", 0) * tax_row.paid_proportion, 2
                ),
                "unreconciled_amount": tax_row.unallocated_amount,
            }
        )


def get_taxes_summary(company, payment_entries):
    gst_accounts = get_all_gst_accounts(company)
    references = [
        advance.reference_name
        for advance in payment_entries
        if advance.reference_type == "Payment Entry"
    ]

    if not references:
        return {}

    gl_entry = frappe.qb.DocType("GL Entry")
    pe = frappe.qb.DocType("Payment Entry")
    taxes = (
        frappe.qb.from_(gl_entry)
        .join(pe)
        .on(pe.name == gl_entry.voucher_no)
        .select(
            Sum(gl_entry.credit_in_account_currency).as_("tax_amount"),
            Sum(gl_entry.debit_in_account_currency).as_("tax_amount_reversed"),
            pe.name.as_("payment_entry"),
            pe.paid_amount,
            pe.unallocated_amount,
        )
        .where(gl_entry.is_cancelled == 0)
        .where(gl_entry.voucher_type == "Payment Entry")
        .where(gl_entry.voucher_no.isin(references))
        .where(gl_entry.account.isin(gst_accounts))
        .where(gl_entry.company == company)
        .groupby(gl_entry.voucher_no)
        .run(as_dict=True)
    )

    taxes = {tax.payment_entry: tax for tax in taxes}

    return taxes
