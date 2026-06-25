# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared helpers for the Input Service Distributor (ISD) feature.

Imports only frappe / pypika / constants so it stays a leaf module that both the
ISD Invoice controller and the ISD reports can depend on (one-directional).
"""

from collections import defaultdict
from datetime import date
from enum import Enum
from functools import reduce
from operator import add

import frappe
from erpnext.accounts.party import get_party_account
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Coalesce, Date, IfNull, Sum
from frappe.utils import add_months, cint, flt, getdate, today

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    IMPORT_GST_CATEGORIES,
)
from india_compliance.gst_india.doctype.turnover_record.turnover_record import upsert_turnover_record

ISD_GST_CATEGORY = "Input Service Distributor"


class CREDIT_FLOW(str, Enum):
    DISTRIBUTION = "Credit Distribution"
    RECEIPT = "Credit Receipt"


def sum_row_tax_by_type(row, prefix):
    """Python float sum of the five GST tax fields on a document/dict row (e.g. distributed_*, total_*)."""
    return sum(flt(getattr(row, f"{prefix}_{tax_type}")) for tax_type in GST_TAX_TYPES)


def throw_row_table(title, header, rows):
    """Raise a ValidationError rendering all offending rows as a table under one title."""
    if not rows:
        return
    frappe.msgprint([header, *rows], title=title, as_table=True, raise_exception=frappe.ValidationError)


def throw_invalid_rows(message, rows):
    """Raise a ValidationError under a descriptive heading, listing the offending row number first
    then the value (like overrides/transaction.py), e.g.
    'Following purchase invoices are not submitted:<br>Row #1: PINV-0001'."""
    if not rows:
        return

    listed = "<br>".join(f"Row #{idx}: {frappe.bold(value)}" for idx, value in rows)
    frappe.throw(_("{0}:<br>{1}").format(message, listed))


def get_pi_total_tax_map(purchase_invoices):
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    return (
        frappe.qb.from_(pi_item)
        .where(pi_item.docstatus == 1)
        .where(pi_item.parent.isin(list(purchase_invoices)))
        .select(
            pi_item.parent,
            Sum(reduce(add, (pi_item[f"{t}_amount"] for t in GST_TAX_TYPES))),
        )
        .groupby(pi_item.parent)
    )


def _diffuse(cumulative, key, raw_amount, precision):
    if not raw_amount:
        return 0.0
    running_raw, running_rounded = cumulative.get(key, (0.0, 0.0))
    new_raw = running_raw + raw_amount
    new_rounded = flt(new_raw, precision)
    cumulative[key] = (new_raw, new_rounded)
    return flt(new_rounded - running_rounded, precision)


def calculate_distribution(doc, cumulative):
    """Set distributed_* fields on each source_invoices row from its distribution_ratio."""
    # https://cleartax.in/s/faqs-on-input-service-distributor-under-gst#:~:text=When%20the%20ISD,the%20other%20state.
    sign = -1 if doc.is_credit_note else 1
    inter_state = is_inter_state_distribution(doc)
    precision = get_field_precision(frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst"))

    for row in doc.source_invoices or []:
        ratio = sign * flt(row.distribution_ratio) / 100  # this ratio is without limiting precision

        bucket = (row.purchase_invoice, cint(row.is_ineligible_for_itc))
        total_igst = flt(row.total_igst)
        total_cgst = flt(row.total_cgst)
        total_sgst = flt(row.total_sgst)
        total_cess = flt(row.total_cess)
        total_cess_non_advol = flt(row.total_cess_non_advol)
        # with flt NoneType is converted to 0.0 before storage
        if inter_state:
            # inter-state -> IGST credit stays IGST, CGST/SGST credit is distributed as IGST (Rule 39(1)(e), (g))
            row.distributed_igst = _diffuse(
                cumulative, (*bucket, "igst"), (total_igst + total_cgst + total_sgst) * ratio, precision
            )
            row.distributed_cgst = 0.0
            row.distributed_sgst = 0.0
        else:
            # intra-state -> IGST credit stays IGST, CGST/SGST credit is distributed as CGST/SGST (Rule 39(1)(e), (f))
            row.distributed_igst = _diffuse(cumulative, (*bucket, "igst"), total_igst * ratio, precision)
            row.distributed_cgst = _diffuse(cumulative, (*bucket, "cgst"), total_cgst * ratio, precision)
            row.distributed_sgst = _diffuse(cumulative, (*bucket, "sgst"), total_sgst * ratio, precision)

        row.distributed_cess = _diffuse(cumulative, (*bucket, "cess"), total_cess * ratio, precision)
        row.distributed_cess_non_advol = _diffuse(
            cumulative, (*bucket, "cess_non_advol"), total_cess_non_advol * ratio, precision
        )


def is_inter_state_distribution(doc):
    # SEZ / overseas recipients are always inter-state (IGST), regardless of place of supply
    party_gst_category = (
        frappe.get_cached_value("Address", doc.party_address, "gst_category") if doc.party_address else None
    )
    if party_gst_category in IMPORT_GST_CATEGORIES:
        return True

    # prefer the place of supply (state number) when both are known -> no extra state lookups
    if doc.company_pos and doc.party_pos:
        return doc.company_pos != doc.party_pos

    # fall back to the addresses' states when a POS is missing
    company_state = (
        frappe.get_cached_value("Address", doc.company_address, "gst_state") if doc.company_address else None
    )
    party_state = (
        frappe.get_cached_value("Address", doc.party_address, "gst_state") if doc.party_address else None
    )
    return company_state != party_state


@frappe.whitelist()
def get_company_isd_gstin(company: str):
    """GSTIN of the first ISD-category address linked to the company (primary address first)."""
    if not company:
        return

    gstins = frappe.get_list(
        "Address",
        filters=[
            ["disabled", "=", 0],
            ["Dynamic Link", "link_doctype", "=", "Company"],
            ["Dynamic Link", "link_name", "=", company],
            ["gst_category", "=", ISD_GST_CATEGORY],
        ],
        pluck="gstin",
        order_by="is_primary_address DESC",
        limit=1,
    )
    return gstins[0] if gstins else None


def validate_common_report_filters(filters):

    filters = frappe._dict(filters or {})

    if filters.company:
        frappe.has_permission("Company", doc=filters.company, throw=True)

    if not filters.from_date or not filters.to_date:
        frappe.throw(
            _("From Date & To Date is mandatory"),
            title=_("Invalid Filter"),
        )

    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))


def get_report_company_currency(filters):
    """Company currency for a report, falling back to the system default currency."""
    if filters.get("company"):
        return frappe.get_cached_value("Company", filters.company, "default_currency")

    return frappe.db.get_default("currency") or "INR"


@frappe.whitelist()
def get_distribution_addresses(party_type: str, party: str, posting_date: str, address: str | None = None):
    if not party_type or not party:
        frappe.throw(_("Party Type and Party are mandatory"))

    frappe.has_permission(party_type, doc=party, ptype="read", throw=True)
    frappe.has_permission("Address", ptype="read", throw=True)

    addr = frappe.qb.DocType("Address")
    dynamic_link = frappe.qb.DocType("Dynamic Link")
    turnover_record = frappe.qb.DocType("Turnover Record")

    query = (
        frappe.qb.from_(addr)
        .join(dynamic_link)
        .on(dynamic_link.parent == addr.name)
        .left_join(turnover_record)
        .on(
            (IfNull(turnover_record.gstin, "") == IfNull(addr.gstin, ""))
            & (IfNull(turnover_record.gst_state, "") == IfNull(addr.gst_state, ""))
        )
        .select(
            addr.name,
            addr.gstin,
            addr.gst_state,
            addr.gst_category,
            Coalesce(turnover_record.amount, 0).as_("turnover_amount"),
        )
        .where(
            (dynamic_link.link_doctype == party_type)
            & (dynamic_link.link_name == party)
            & (addr.gst_category != ISD_GST_CATEGORY)
        )
        .where(
            (turnover_record.from_date.isnull())
            | (Date(add_months(posting_date, -1))).between(turnover_record.from_date, turnover_record.to_date)
        )
    )

    if address:
        query = query.where(addr.name == address)

    return query.run(as_dict=True)


def make_isd_invoice(
    source_purchase_invoices: list,
    company_address: str,
    party_address: str,
    party_type: str | None = None,
    party: str | None = None,
    individual_turnover: float | None = None,
    total_turnover: float | None = None,
    posting_date: date | None = None,
    cumulative: dict | None = None,
):
    """source_purchase_invoices: list of dicts (from get_purchase_invoices_distribution_summary),
    one per (purchase_invoice, is_ineligible_for_itc), each with:
        purchase_invoice, is_ineligible_for_itc, total_<tax>, available_<tax>, total_tax, available_tax
    """
    if not source_purchase_invoices:
        frappe.throw(_("No source Purchase Invoices to distribute."))

    if not posting_date:
        posting_date = today()

    is_against_party = 1 if party_type in ["Customer", "Supplier"] and party else 0
    turnover_ratio = individual_turnover / total_turnover if individual_turnover and total_turnover else 0.0

    seed_name = source_purchase_invoices[0]["purchase_invoice"]
    company = frappe.db.get_value("Purchase Invoice", seed_name, "company")

    doc = frappe.new_doc("ISD Invoice")
    doc.company = company
    doc.posting_date = posting_date
    doc.company_address = company_address
    doc.party_address = party_address
    doc.default_distribution_ratio = turnover_ratio * 100

    for prefix, address in (("company", company_address), ("party", party_address)):
        if not address:
            frappe.throw(_("Address is required"))
        gstin, state_number, state = frappe.db.get_value(
            "Address", address, ["gstin", "gst_state_number", "gst_state"]
        )
        doc.set(f"{prefix}_gstin", gstin)
        doc.set(f"{prefix}_pos", f"{state_number}-{state}")
        if prefix == "party" and not gstin and not is_against_party:
            doc.expense_account = frappe.get_cached_value("Company", company, "default_gst_expense_account")
            doc.cost_center = frappe.db.get_value("Company", company, "cost_center")

    if party_type and party:  # party_type can be company or customer or supplier
        doc.is_against_party = is_against_party
        doc.party_type = party_type
        doc.party = party
        if is_against_party:
            doc.credit_flow = CREDIT_FLOW.DISTRIBUTION
            doc.party_account = get_party_account(doc.party_type, doc.party, doc.company)

    for pi in source_purchase_invoices:
        total_tax = flt(pi.total_tax)
        if not total_tax:
            continue
        scale = flt(pi.available_tax) / total_tax
        doc.append(
            "source_invoices",
            {
                "purchase_invoice": pi.purchase_invoice,
                "is_ineligible_for_itc": pi.is_ineligible_for_itc,
                **{f"total_{t}": pi[f"total_{t}"] for t in GST_TAX_TYPES},
                "distribution_ratio": turnover_ratio
                * scale
                * 100,  # assuming rounding will happen automatically on save
            },
        )

    calculate_distribution(doc, cumulative)
    doc.set_taxes_and_totals()
    doc.set_address_display()  # bulk save runs with ignore_validate, which skips validate()
    return doc


def get_distribution_summary_query(purchase_invoices: list | str | None = None):
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    isd_invoice = frappe.qb.DocType("ISD Invoice")

    # already-distributed tax per (purchase invoice, eligibility). A PI is only ever distributed under
    # its own GSTIN (enforced on the ISD Invoice), so no company_gstin match is needed here.
    distributed = (
        frappe.qb.from_(isd_source_item)
        .join(isd_invoice)
        .on(isd_source_item.parent == isd_invoice.name)
        .where(isd_source_item.docstatus == 1)
        .where(
            (isd_invoice.is_against_party == 0)
            | (
                (isd_invoice.is_against_party == 1)
                & (isd_invoice.credit_flow == CREDIT_FLOW.DISTRIBUTION.value)
            )
        )
        .select(
            isd_source_item.purchase_invoice,
            isd_source_item.is_ineligible_for_itc,
            *[
                Sum(getattr(isd_source_item, f"distributed_{t}")).as_(f"distributed_{t}")
                for t in GST_TAX_TYPES
            ],
        )
        .groupby(isd_source_item.purchase_invoice, isd_source_item.is_ineligible_for_itc)
    )
    if purchase_invoices:
        distributed = distributed.where(isd_source_item.purchase_invoice.isin(purchase_invoices))
    distributed = distributed.as_("distributed")

    # one row per (purchase_invoice, is_ineligible_for_itc):
    # {purchase_invoice, is_ineligible_for_itc, *total_, total_tax, available_tax}
    query = (
        frappe.qb.from_(pi_item)
        .left_join(distributed)
        .on(
            (distributed.purchase_invoice == pi_item.parent)
            & (distributed.is_ineligible_for_itc == pi_item.is_ineligible_for_itc)
        )
        .where(pi_item.docstatus == 1)
        .select(
            pi_item.parent.as_("purchase_invoice"),
            pi_item.is_ineligible_for_itc,
            *[Coalesce(Sum(getattr(pi_item, f"{t}_amount")), 0).as_(f"total_{t}") for t in GST_TAX_TYPES],
            reduce(add, (Coalesce(Sum(getattr(pi_item, f"{t}_amount")), 0) for t in GST_TAX_TYPES)).as_(
                "total_tax"
            ),
            reduce(add, (Coalesce(getattr(distributed, f"distributed_{t}"), 0) for t in GST_TAX_TYPES)).as_(
                "distributed_tax"
            ),
            reduce(
                add,
                (
                    Coalesce(Sum(getattr(pi_item, f"{t}_amount")), 0)
                    - Coalesce(getattr(distributed, f"distributed_{t}"), 0)
                    for t in GST_TAX_TYPES
                ),
            ).as_("available_tax"),
        )
        .groupby(pi_item.parent, pi_item.is_ineligible_for_itc)
    )
    if purchase_invoices:
        query = query.where(pi_item.parent.isin(purchase_invoices))

    return query


@frappe.whitelist()
def get_purchase_invoices_distribution_summary(purchase_invoices: list | str):
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    return _get_purchase_invoices_distribution_summary(purchase_invoices)


def _get_purchase_invoices_distribution_summary(purchase_invoices: list | str):
    if not purchase_invoices:
        return []

    return get_distribution_summary_query(purchase_invoices).run(as_dict=True)


@frappe.whitelist()
def bulk_create_isd_invoices(
    distribution_table: list | str, purchase_invoices: list | str, posting_date: str
):
    """Create ISD invoices distributing the given purchase invoices' tax across addresses."""

    frappe.has_permission("ISD Invoice", "write", throw=True)
    frappe.has_permission("Purchase Invoice", "read", throw=True)

    if isinstance(distribution_table, str):
        distribution_table = frappe.parse_json(distribution_table)
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)
    if isinstance(posting_date, str):
        posting_date = getdate(posting_date)

    if not purchase_invoices:
        frappe.throw(_("No Purchase Invoices provided."))

    # Ensure purchase_invoices is a list of names (strings), not objects
    if purchase_invoices and isinstance(purchase_invoices[0], dict):
        frappe.throw(_("Purchase Invoices must be passed as list of names, not full objects."))

    # drop addresses with no turnover - they would distribute nothing
    distribution_table = [row for row in distribution_table if flt(row["turnover_amount"] or 0)]

    # bulk groups source invoices by billing address, so join Purchase Invoice for it
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    source_purchase_invoices = (
        get_distribution_summary_query(purchase_invoices)
        .join(pi)
        .on(pi.name == pi_item.parent)
        .select(pi.billing_address)
        .run(as_dict=True)
    )

    total_turnover = sum(flt(row.get("turnover_amount") or 0) for row in distribution_table)

    by_billing = defaultdict(list)
    for pi_row in source_purchase_invoices:
        by_billing[pi_row.billing_address].append(pi_row)

    invoice_tasks = []
    for pi_group in by_billing.values():
        for row in distribution_table:
            invoice_tasks.append((pi_group, row))
    # invoice tasks [(pi with same billing address, addresses with turnover to distribute to)]

    # adjust rounding per (purchase invoice, eligibility) bucket
    invoices, invalid_invoices = [], []
    isd_doc = None
    cumulative = {}
    for pi_group, row in invoice_tasks:
        isd_doc = make_isd_invoice(
            source_purchase_invoices=pi_group,
            company_address=pi_group[0].billing_address,
            party_address=row["party_address"],
            party_type=row["party_type"],
            party=row["party"],
            individual_turnover=flt(row["turnover_amount"]),
            total_turnover=total_turnover,
            posting_date=posting_date,
            cumulative=cumulative,
        )
        is_invalid_invoice = False
        messages_before = len(frappe.message_log)
        try:
            isd_doc.validate_purchase_invoices()
            isd_doc.validate_addresses()
        except frappe.ValidationError:
            del frappe.message_log[messages_before:]
            is_invalid_invoice = True

        isd_doc.flags.ignore_validate = True
        isd_doc.save()

        if is_invalid_invoice:
            invalid_invoices.append(isd_doc.name)
        invoices.append(isd_doc.name)

    frappe.enqueue(
        _upsert_turnover_records,
        queue="short",
        distribution_table=distribution_table,
        posting_date=posting_date,
        enqueue_after_commit=True,
    )

    return invoices, invalid_invoices


def _upsert_turnover_records(distribution_table, posting_date):

    for row in distribution_table:
        upsert_turnover_record(
            gstin=row["gstin"],
            gst_state=row["gst_state"],
            amount=row["turnover_amount"],
            posting_date=posting_date,
        )
