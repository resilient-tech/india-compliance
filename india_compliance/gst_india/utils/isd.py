# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared helpers for the Input Service Distributor (ISD) feature.

Imports only frappe / constants so it stays a leaf module that the ISD controllers can depend on
(one-directional).
"""

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import cint, flt

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    IMPORT_GST_CATEGORIES,
)
from india_compliance.gst_india.doctype.turnover_record.turnover_record import get_turnover_amount
from india_compliance.gst_india.utils import get_gst_accounts_by_type

ISD_GST_CATEGORY = "Input Service Distributor"


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


def should_distribute_expense():
    return cint(frappe.get_cached_value("GST Settings", "GST Settings", "distribute_expense_with_isd_credit"))


def get_row_itc(row, is_distribution, precision, ratio=None):
    """Row-wise ITC per GST head.

    distribution side -> drawn from the source heads: ``flt(total_<head> * ratio)``
    recipient side    -> the already-converted amounts: ``flt(distributed_<head>)``
    """
    if is_distribution:
        return {
            gst_tax_type: flt(flt(row.get(f"total_{gst_tax_type}")) * ratio, precision)
            for gst_tax_type in GST_TAX_TYPES
        }
    return {
        gst_tax_type: flt(row.get(f"distributed_{gst_tax_type}"), precision) for gst_tax_type in GST_TAX_TYPES
    }


def calculate_distribution(doc):
    ratio = get_distribution_ratio(doc)
    inter_state = is_inter_state_distribution(doc)
    distribute_expense = should_distribute_expense()

    meta = frappe.get_meta("ISD Source Item")
    precision = get_field_precision(meta.get_field("distributed_igst"))
    expense_precision = get_field_precision(meta.get_field("distributed_expense"))

    for row in doc.source_items or []:
        credit = get_row_itc(row, True, precision, ratio)

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
        row.distributed_expense = (
            flt(flt(row.total_expense) * ratio, expense_precision) if distribute_expense else 0.0
        )


@frappe.whitelist()
def get_source_items_from_purchase_invoice(purchase_invoice: str):
    frappe.has_permission("Purchase Invoice", "read", doc=purchase_invoice, throw=True)

    if not purchase_invoice:
        return []

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


# ---------------------------------------------------------------------------- autofill
# The party chain both ISD doctypes share
_PARTY_CHAIN = ("company", "is_against_party", "party_type", "party")


def _resolve_isd_party_type(doc, is_company_isd):
    if not doc.is_against_party:
        return None
    # by default distribution passes credit to an internal Customer; the recipient receives it from an internal Supplier
    return "Customer" if is_company_isd else "Supplier"


def _resolve_isd_party(doc):
    if not (doc.is_against_party and doc.party_type):
        return None

    internal_field = "is_internal_customer" if doc.party_type == "Customer" else "is_internal_supplier"
    parties = frappe.get_list(
        doc.party_type, filters={internal_field: 1, "disabled": 0}, pluck="name", limit=1
    )
    return parties[0] if parties else None


def _fetch_isd_address(link_doctype, link_name, *, isd):
    """First enabled address of the owner, with the ISD / non-ISD gst_category as required."""
    if not link_name:
        return None

    results = frappe.get_list(
        "Address",
        filters=[
            ["disabled", "=", 0],
            ["Dynamic Link", "link_doctype", "=", link_doctype],
            ["Dynamic Link", "link_name", "=", link_name],
            ["gst_category", "=" if isd else "!=", ISD_GST_CATEGORY],
        ],
        pluck="name",
        order_by="is_primary_address DESC",
        limit=1,
    )
    return results[0] if results else None


def _resolve_isd_provisional_account(doc):
    if not doc.company:
        return None

    if not doc.is_against_party:
        return frappe.get_cached_value("Company", doc.company, "default_isd_provisional_account")

    if not doc.party_type:
        return None

    # leaf module: import lazily to avoid pulling erpnext at import time
    from erpnext.accounts.party import get_party_account

    return get_party_account(doc.party_type, doc.party, doc.company)


def _resolve_isd_addresses(doc, is_distribution_side):
    """Return (distribution_address, recipient_address)."""
    if not doc.company:
        return None, None

    # single-company setup: both addresses belong to the company
    if not doc.is_against_party:
        return (
            _fetch_isd_address("Company", doc.company, isd=True),
            _fetch_isd_address("Company", doc.company, isd=False),
        )

    company_isd_address = _fetch_isd_address("Company", doc.company, isd=is_distribution_side)

    # counterparty side needs a party; still fill the company-owned side meanwhile
    party_address = None
    if doc.party_type and doc.party:
        party_address = _fetch_isd_address(doc.party_type, doc.party, isd=not is_distribution_side)

    if is_distribution_side:
        # company -> distribution (ISD); party -> recipient (non-ISD)
        return company_isd_address, party_address
    # recipient invoice: company -> recipient (non-ISD); party -> distribution (ISD)
    return party_address, company_isd_address


def _resolve_recipient_branch_turnover(doc):
    if not doc.recipient_address:
        return doc.branch_turnover

    gstin, gst_state = frappe.get_cached_value("Address", doc.recipient_address, ["gstin", "gst_state"])

    return get_turnover_amount(gstin, gst_state, doc.posting_date)


@frappe.whitelist()
def get_isd_autofill_values(doctype: str, changed_field: str, doc: str | dict):
    """Single-call autofill for both ISD doctypes"""
    doc = frappe._dict(frappe.parse_json(doc))
    doc.is_against_party = cint(doc.is_against_party)
    is_distribution_side = doctype == "ISD Distribution Invoice"

    if changed_field in _PARTY_CHAIN:
        downstream = _PARTY_CHAIN[_PARTY_CHAIN.index(changed_field) + 1 :]
        if "party_type" in downstream:
            doc.party_type = _resolve_isd_party_type(doc, is_distribution_side)
        if "party" in downstream:
            doc.party = _resolve_isd_party(doc)

        doc.isd_provisional_account = _resolve_isd_provisional_account(doc)
        doc.distribution_address, doc.recipient_address = _resolve_isd_addresses(doc, is_distribution_side)

    if is_distribution_side:
        doc.branch_turnover = (
            _resolve_recipient_branch_turnover(doc) or doc.branch_turnover
        )  # if no turnover is found don't override

    return doc
