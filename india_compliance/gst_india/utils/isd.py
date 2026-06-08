# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Shared helpers for the Input Service Distributor (ISD) feature.

Imports only frappe / pypika / constants so it stays a leaf module that both the
ISD Invoice controller and the ISD reports can depend on (one-directional).
"""

from functools import reduce
from operator import add

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.query_builder.functions import Sum
from frappe.utils import flt

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    IMPORT_GST_CATEGORIES,
)


def sum_row_tax_by_type(row, prefix):
    """Python float sum of the five GST tax fields on a document/dict row (e.g. distributed_*, total_*)."""
    return sum(flt(getattr(row, f"{prefix}_{tax_type}")) for tax_type in GST_TAX_TYPES)


def get_isd_source_item_query(purchase_invoices=None):
    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    isd_invoice = frappe.qb.DocType("ISD Invoice")

    query = (
        frappe.qb.from_(isd_source_item)
        .join(isd_invoice)
        .on(isd_source_item.parent == isd_invoice.name)
        .select(
            isd_source_item.purchase_invoice,
            Sum(reduce(add, (isd_source_item[f"distributed_{t}"] for t in GST_TAX_TYPES))).as_(
                "total_distributed"
            ),
        )
        .where(isd_invoice.docstatus == 1)
        .groupby(isd_source_item.purchase_invoice)
    )

    if purchase_invoices is not None:
        query = query.where(isd_source_item.purchase_invoice.isin(purchase_invoices))

    return query


def calculate_distribution(doc):
    """Set distributed_* fields on each source_invoices row from its distribution_ratio."""
    sign = -1 if doc.is_credit_note else 1
    inter_state = is_inter_state_distribution(doc)
    precision = get_field_precision(frappe.get_meta("ISD Invoice Source Item").get_field("distributed_igst"))

    for row in doc.source_invoices or []:
        ratio = sign * flt(row.distribution_ratio) / 100

        if inter_state:
            row.distributed_igst = flt(
                (flt(row.total_cgst) + flt(row.total_sgst) + flt(row.total_igst)) * ratio, precision
            )
            row.distributed_cgst = 0.0
            row.distributed_sgst = 0.0
        else:
            row.distributed_igst = flt(flt(row.total_igst) * ratio, precision)
            row.distributed_cgst = flt(flt(row.total_cgst) * ratio, precision)
            row.distributed_sgst = flt(flt(row.total_sgst) * ratio, precision)

        row.distributed_cess = flt(flt(row.total_cess) * ratio, precision)
        row.distributed_cess_non_advol = flt(flt(row.total_cess_non_advol) * ratio, precision)


def is_inter_state_distribution(doc):

    if doc.company_pos and doc.party_pos:
        return doc.company_pos != doc.party_pos

    company_state = (
        frappe.db.get_value("Address", doc.company_address, "gst_state") if doc.company_address else None
    )
    party_state, party_gst_category = (
        frappe.db.get_value("Address", doc.party_address, ["gst_state", "gst_category"])
        if doc.party_address
        else (None, None)
    )

    return company_state != party_state or party_gst_category in IMPORT_GST_CATEGORIES


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
