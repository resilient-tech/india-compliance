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
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Coalesce, Date, IfNull, Sum
from frappe.utils import flt, getdate, today

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    IMPORT_GST_CATEGORIES,
)

ISD_GST_CATEGORY = "Input Service Distributor"


class CREDIT_FLOW(str, Enum):
    DISTRIBUTION = "Credit Distribution"
    RECEIPT = "Credit Receipt"


def sum_row_tax_by_type(row, prefix):
    """Python float sum of the five GST tax fields on a document/dict row (e.g. distributed_*, total_*)."""
    return sum(flt(getattr(row, f"{prefix}_{tax_type}")) for tax_type in GST_TAX_TYPES)


def get_isd_source_item_query(purchase_invoices=None):
    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")

    query = (
        frappe.qb.from_(isd_source_item)
        .select(
            isd_source_item.purchase_invoice,
            Sum(reduce(add, (isd_source_item[f"distributed_{t}"] for t in GST_TAX_TYPES))).as_(
                "total_distributed"
            ),
        )
        .where(isd_source_item.docstatus == 1)
    )

    if purchase_invoices is not None:
        query = query.where(isd_source_item.purchase_invoice.isin(purchase_invoices))

    return query


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


def calculate_distribution(doc):
    """Set distributed_* fields on each source_invoices row from its distribution_ratio."""
    sign = -1 if doc.is_credit_note else 1
    inter_state = is_inter_state_distribution(doc)
    precision = get_field_precision(frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst"))

    for row in doc.source_invoices or []:
        ratio = sign * flt(row.distribution_ratio) / 100

        # inter-state -> all IGST; intra-state -> CGST + SGST (equal halves, since the rates are equal)
        pool = flt((flt(row.total_cgst) + flt(row.total_sgst) + flt(row.total_igst)) * ratio, precision)

        if inter_state:
            row.distributed_igst = pool
            row.distributed_cgst = 0.0
            row.distributed_sgst = 0.0
        else:
            cgst = flt(pool / 2, precision)
            row.distributed_cgst = cgst
            row.distributed_sgst = flt(pool - cgst, precision)
            row.distributed_igst = 0.0

        row.distributed_cess = flt(flt(row.total_cess) * ratio, precision)
        row.distributed_cess_non_advol = flt(flt(row.total_cess_non_advol) * ratio, precision)


def is_inter_state_distribution(doc):
    party_gst_category = (
        frappe.db.get_value("Address", doc.party_address, "gst_category") if doc.party_address else None
    )

    # SEZ / overseas recipients are always inter-state (IGST), regardless of place of supply
    if party_gst_category in IMPORT_GST_CATEGORIES:
        return True

    if doc.company_pos and doc.party_pos:
        return doc.company_pos != doc.party_pos

    company_state = (
        frappe.db.get_value("Address", doc.company_address, "gst_state") if doc.company_address else None
    )
    party_state = (
        frappe.db.get_value("Address", doc.party_address, "gst_state") if doc.party_address else None
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
            | (Date(posting_date).between(turnover_record.from_date, turnover_record.to_date))
        )
    )

    if address:
        query = query.where(addr.name == address)

    return query.run(as_dict=True)


def make_isd_invoice(
    source_purchase_invoices: list,
    company_address: str,
    party_address: str | None = None,
    party_type: str | None = None,
    party: str | None = None,
    individual_turnover: float | None = None,
    total_turnover: float | None = None,
    posting_date: date | None = None,
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
            continue
        gstin, state_number, state = frappe.db.get_value(
            "Address", address, ["gstin", "gst_state_number", "gst_state"]
        )
        doc.set(f"{prefix}_gstin", gstin)
        doc.set(f"{prefix}_pos", f"{state_number}-{state}")
        if prefix == "party" and not gstin:
            doc.expense_account = frappe.db.get_value("Company", company, "default_gst_expense_account")
            doc.cost_center = frappe.db.get_value("Company", company, "cost_center")

    if party_type and party:
        doc.is_against_party = is_against_party
        doc.party_type = party_type
        doc.party = party
        if is_against_party:
            doc.credit_flow = CREDIT_FLOW.DISTRIBUTION

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
                "distribution_ratio": turnover_ratio * scale * 100,
            },
        )

    calculate_distribution(doc)
    doc.set_taxes_and_totals()
    return doc


@frappe.whitelist()
def get_purchase_invoices_distribution_summary(
    purchase_invoices: list | str, extra_fields: list | str | None = None
):
    """Per purchase invoice: posting date, supplier, total tax and tax still available to distribute"""
    frappe.has_permission("Purchase Invoice", "read", throw=True)
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    if not purchase_invoices:
        return []

    if isinstance(extra_fields, str):
        extra_fields = frappe.parse_json(extra_fields)

    valid_pi_columns = set(frappe.get_meta("Purchase Invoice").get_valid_columns())
    extra_fields = [f for f in (extra_fields or []) if f in valid_pi_columns]

    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    isd_invoice = frappe.qb.DocType("ISD Invoice")

    distributed = (
        frappe.qb.from_(isd_source_item)
        .join(isd_invoice)
        .on(isd_source_item.parent == isd_invoice.name)
        .where(isd_source_item.docstatus == 1)
        .where(isd_source_item.purchase_invoice.isin(purchase_invoices))
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
            isd_invoice.company_gstin,
            *[
                Sum(getattr(isd_source_item, f"distributed_{t}")).as_(f"distributed_{t}")
                for t in GST_TAX_TYPES
            ],
        )
        .groupby(
            isd_source_item.purchase_invoice,
            isd_source_item.is_ineligible_for_itc,
            isd_invoice.company_gstin,
        )
    ).as_("distributed")

    # list of dicts, one per (purchase_invoice, is_ineligible_for_itc):
    # {purchase_invoice, supplier, posting_date, billing_address, is_ineligible_for_itc, *total_, *available_}
    source_purchase_invoices = (
        frappe.qb.from_(pi_item)
        .join(pi)
        .on(pi.name == pi_item.parent)
        .left_join(distributed)
        .on(
            (distributed.purchase_invoice == pi_item.parent)
            & (distributed.is_ineligible_for_itc == pi_item.is_ineligible_for_itc)
            & (distributed.company_gstin == pi.company_gstin)
        )
        .where(pi_item.docstatus == 1)
        .where(pi_item.parent.isin(purchase_invoices))
        .select(
            pi.name.as_("purchase_invoice"),
            pi.supplier,
            pi.posting_date,
            pi.billing_address,
            pi_item.is_ineligible_for_itc,
            *[getattr(pi, f) for f in extra_fields],
            *[Coalesce(Sum(getattr(pi_item, f"{t}_amount")), 0).as_(f"total_{t}") for t in GST_TAX_TYPES],
            *[
                (
                    Coalesce(Sum(getattr(pi_item, f"{t}_amount")), 0)
                    - Coalesce(getattr(distributed, f"distributed_{t}"), 0)
                ).as_(f"available_{t}")
                for t in GST_TAX_TYPES
            ],
        )
        .groupby(pi_item.parent, pi_item.is_ineligible_for_itc)
        .run(as_dict=True)
    )

    for row in source_purchase_invoices:
        row["total_tax"] = sum(row[f"total_{t}"] for t in GST_TAX_TYPES)
        row["available_tax"] = sum(row[f"available_{t}"] for t in GST_TAX_TYPES)

    return source_purchase_invoices


@frappe.whitelist()
def bulk_create_isd_invoices(
    distribution_table: list | str, purchase_invoices: list | str, posting_date: str
):
    """Create ISD invoices distributing the given purchase invoices' tax across addresses."""
    # local imports avoid a circular dependency on the ISD Invoice controller / turnover doctype
    from india_compliance.gst_india.doctype.isd_invoice.isd_invoice import (
        _validate_isd_invoice_for_bulk_generation,
    )
    from india_compliance.gst_india.doctype.turnover_record.turnover_record import upsert_turnover_record

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

    _tax_precision = get_field_precision(
        frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst")
    )  # assuming every tax row have same precision

    # drop addresses with no turnover - they would distribute nothing
    distribution_table = [row for row in distribution_table if flt(row["turnover_amount"] or 0)]

    # [{purchase_invoice: ,billing_address: ,is_ineligible_for_itc: , *total_, *available_}]
    source_purchase_invoices = get_purchase_invoices_distribution_summary(purchase_invoices)

    total_turnover = sum(flt(row.get("turnover_amount") or 0) for row in distribution_table)

    total_available_for_distribution = flt(0, _tax_precision)

    by_billing = defaultdict(list)
    for pi in source_purchase_invoices:
        by_billing[pi.billing_address].append(pi)

        total_available_for_distribution += pi.available_tax

    invoice_tasks = []
    for pi_group in by_billing.values():
        for row in distribution_table:
            invoice_tasks.append((pi_group, row))

    invoices, invalid_invoices = [], []
    total_distributed = flt(0, _tax_precision)
    isd_doc = None
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
        )
        is_invalid_invoice = False
        messages_before = len(frappe.message_log)
        try:
            _validate_isd_invoice_for_bulk_generation(isd_doc)
        except frappe.ValidationError:
            del frappe.message_log[messages_before:]
            is_invalid_invoice = True

        isd_doc.flags.ignore_validate = True
        isd_doc.save()

        if is_invalid_invoice:
            invalid_invoices.append(isd_doc.name)
        invoices.append(isd_doc.name)
        total_distributed += sum(sum_row_tax_by_type(src, "distributed") for src in isd_doc.source_invoices)

    if isd_doc and (
        rounding_difference := flt(total_available_for_distribution - total_distributed, _tax_precision)
    ):
        item_to_adjust_rounding = isd_doc.source_invoices[0]
        valid_distributed_fields = [
            f"distributed_{t}" for t in GST_TAX_TYPES if item_to_adjust_rounding.get(f"distributed_{t}")
        ]
        field = valid_distributed_fields[0] if valid_distributed_fields else f"distributed_{GST_TAX_TYPES[0]}"
        item_to_adjust_rounding.set(
            field,
            flt(item_to_adjust_rounding.get(field) + rounding_difference, _tax_precision),
        )
        isd_doc.flags.ignore_validate = True
        isd_doc.save()

    for row in distribution_table:
        frappe.enqueue(
            upsert_turnover_record,
            queue="short",
            gstin=row["gstin"],
            gst_state=row["gst_state"],
            amount=row["turnover_amount"],
        )

    return invoices, invalid_invoices
