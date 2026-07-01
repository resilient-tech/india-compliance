# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared helpers for the Input Service Distributor (ISD) feature.

Imports only frappe / constants so it stays a leaf module that the ISD controllers can depend on
(one-directional).
"""

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import flt

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    IMPORT_GST_CATEGORIES,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type

ISD_GST_CATEGORY = "Input Service Distributor"
ISD_DISTRIBUTION_PROVISIONAL_ACCOUNT = "ISD Distribution Provisional"


def sum_row_tax_by_type(row, prefix):
    """Python float sum of the five GST tax fields on a document/dict row (e.g. distributed_*, total_*)."""
    return sum(flt(row.get(f"{prefix}_{tax_type}")) for tax_type in GST_TAX_TYPES)


def throw_row_table(title, header, rows):
    """Raise a ValidationError rendering all offending rows as a table under one title."""
    if not rows:
        return
    table = [[str(cell) for cell in row] for row in ([header, *rows])]
    frappe.msgprint(table, title=title, as_table=True, raise_exception=frappe.ValidationError)


def throw_invalid_rows(message, rows):
    """Raise a ValidationError under a descriptive heading, listing the offending row number first
    then the value, e.g. 'Following purchase invoices are not submitted:<br>Row #1: PINV-0001'."""
    if not rows:
        return

    listed = "<br>".join(f"Row #{idx}: {frappe.bold(value)}" for idx, value in rows)
    frappe.throw(_("{0}:<br>{1}").format(message, listed))


def is_inter_state_distribution(doc):
    # SEZ / overseas recipients are always inter-state (IGST), regardless of place of supply
    party_gst_category = (
        frappe.get_cached_value("Address", doc.recipient_address, "gst_category")
        if doc.recipient_address
        else None
    )
    if party_gst_category in IMPORT_GST_CATEGORIES:
        return True

    # prefer the place of supply (state number) when both are known -> no extra state lookups
    if doc.distribution_pos and doc.recipient_pos:
        return doc.distribution_pos != doc.recipient_pos

    # fall back to the addresses' states when a POS is missing
    company_state = (
        frappe.get_cached_value("Address", doc.distribution_address, "gst_state")
        if doc.distribution_address
        else None
    )
    party_state = (
        frappe.get_cached_value("Address", doc.recipient_address, "gst_state")
        if doc.recipient_address
        else None
    )
    return company_state != party_state


def get_distribution_ratio(doc):
    """Signed turnover ratio (credit notes reverse credit, so they carry a negative sign)."""
    sign = -1 if doc.is_credit_note else 1
    return sign * flt(doc.branch_turnover / doc.total_turnover)


def get_source_head_itc(row, ratio, precision):
    """ITC drawn from each *source* GST account for this row: ``flt(total_<head> * ratio)``."""
    return {
        gst_tax_type: flt(flt(row.get(f"total_{gst_tax_type}")) * ratio, precision)
        for gst_tax_type in GST_TAX_TYPES
    }


def calculate_distribution(doc):
    ratio = get_distribution_ratio(doc)
    inter_state = is_inter_state_distribution(doc)

    meta = frappe.get_meta("ISD Source Item")
    precision = get_field_precision(meta.get_field("distributed_igst"))
    expense_precision = get_field_precision(meta.get_field("distributed_expense"))

    for row in doc.source_invoices or []:
        credit = get_source_head_itc(row, ratio, precision)

        if inter_state:
            # inter-state -> the recipient receives everything as IGST (Rule 39(1)(e), (g)).
            # Sum the already-rounded parts so distributed_igst == CGST + SGST + IGST booked in taxes.
            row.distributed_igst = flt(credit["igst"] + credit["cgst"] + credit["sgst"], precision)
            row.distributed_cgst = 0.0
            row.distributed_sgst = 0.0
        else:
            # intra-state -> each credit keeps its type (Rule 39(1)(e), (f))
            row.distributed_igst = credit["igst"]
            row.distributed_cgst = credit["cgst"]
            row.distributed_sgst = credit["sgst"]

        # cess is never fused, whatever the place of supply
        row.distributed_cess = credit["cess"]
        row.distributed_cess_non_advol = credit["cess_non_advol"]
        row.distributed_expense = flt(flt(row.total_expense) * ratio, expense_precision)


@frappe.whitelist()
def get_source_items_from_purchase_invoice(purchase_invoice):
    frappe.has_permission("Purchase Invoice", "read", doc=purchase_invoice, throw=True)

    pi_items = frappe.get_all(
        "Purchase Invoice Item",
        filters={"parent": purchase_invoice},
        fields=[
            "name",
            "item_code",
            "item_name",
            "gst_hsn_code",
            "is_ineligible_for_itc",
            "cost_center",
            "project",
            "expense_account",
            "base_net_amount",
            "igst_amount",
            "cgst_amount",
            "sgst_amount",
            "cess_amount",
            "cess_non_advol_amount",
        ],
        order_by="idx",
    )

    source_items = []
    for item in pi_items:
        source_items.append(
            {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "gst_hsn_code": item.gst_hsn_code,
                "purchase_invoice_item": item.name,
                "is_ineligible_for_itc": item.is_ineligible_for_itc,
                "cost_center": item.cost_center,
                "project": item.project,
                "expense_head": item.expense_account,
                "total_expense": item.base_net_amount,
                "total_igst": item.igst_amount,
                "total_cgst": item.cgst_amount,
                "total_sgst": item.sgst_amount,
                "total_cess": item.cess_amount,
                "total_cess_non_advol": item.cess_non_advol_amount,
            }
        )

    return source_items


@frappe.whitelist()
def get_input_gst_accounts(company: str):
    return get_gst_accounts_by_type(company, "Input")
