# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt
from pypika.terms import Case

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils.isd import (
    CREDIT_FLOW,
    get_distribution_summary_query,
    get_report_company_currency,
    validate_common_report_filters,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if filters.get("date_range"):
        filters.from_date, filters.to_date = filters.date_range
    validate_common_report_filters(filters)

    if filters.get("show_distribution"):
        return get_distribution_columns(filters), get_distribution_data(filters), None, None, None, 1

    return get_pi_columns(filters), get_pi_data(filters)


def _apply_company_filter(query, doctype, filters):
    if filters.get("company"):
        return query.where(doctype.company == filters.company)

    permitted = get_permitted_documents("Company")
    if permitted:
        return query.where(doctype.company.isin(permitted))

    return query


# Purchase invoice view (show_distribution=0)


def get_pi_data(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    query = (
        get_distribution_summary_query()
        .join(pi)
        .on(pi.name == pi_item.parent)
        .select(pi.company_gstin, pi.place_of_supply)
        .where(pi.is_isd_applicable == 1)
        .where(pi.posting_date[filters.from_date : filters.to_date])
        .orderby(pi.posting_date)
    )
    query = _apply_company_filter(query, pi, filters)
    if filters.get("company_gstin"):
        query = query.where(pi.company_gstin == filters.company_gstin)

    # collapse the per-(pi, is_ineligible) summary into one row per purchase invoice (posting-date order)
    rows = {}
    for row in query.run(as_dict=True):
        pi_row = rows.setdefault(
            row.purchase_invoice,
            frappe._dict(
                purchase_invoice=row.purchase_invoice,
                company_gstin=row.company_gstin,
                place_of_supply=row.place_of_supply,
                total_tax=0.0,
                available_eligible=0.0,
                available_ineligible=0.0,
            ),
        )

        pi_row.total_tax += flt(row.total_tax)
        if cint(row.is_ineligible_for_itc):
            pi_row.available_ineligible += flt(row.available_tax)
        else:
            pi_row.available_eligible += flt(row.available_tax)

    data = []
    for pi_row in rows.values():
        pi_row.available_total = pi_row.available_eligible + pi_row.available_ineligible

        # pending_distribution: keep only PIs that still have credit to distribute
        if filters.get("pending_distribution") and pi_row.available_total <= 0:
            continue

        data.append(pi_row)

    return data


def get_pi_columns(filters):
    company_currency = get_report_company_currency(filters)

    return [
        {
            "fieldname": "purchase_invoice",
            "label": _("Invoice No"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 220,
        },
        {
            "fieldname": "company_gstin",
            "label": _("Company GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "place_of_supply",
            "label": _("POS"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "total_tax",
            "label": _("Total Tax"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "available_total",
            "label": _("Available for Distribution"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 180,
        },
        {
            "fieldname": "available_eligible",
            "label": _("Eligible Available"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150,
        },
        {
            "fieldname": "available_ineligible",
            "label": _("Ineligible Available"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150,
        },
    ]


# distributed view
def _get_pi_distribution(filters):
    """Distribution detail: one row per (ISD invoice, purchase invoice, eligibility) from submitted ISD invoices."""
    isi = frappe.qb.DocType("ISD Invoice Source Item")
    isd = frappe.qb.DocType("ISD Invoice")

    # Receipt-side inter-company invoice has company/party GSTINs inverted relative to the
    # distribution side, so normalise: distributor is always the ISD address, recipient the other.
    is_receipt = (isd.is_against_party == 1) & (isd.credit_flow == CREDIT_FLOW.RECEIPT.value)
    distributor_gstin = Case().when(is_receipt, isd.party_gstin).else_(isd.company_gstin)
    recipient_gstin = Case().when(is_receipt, isd.company_gstin).else_(isd.party_gstin)

    query = (
        frappe.qb.from_(isi)
        .join(isd)
        .on(isi.parent == isd.name)
        .where(isi.docstatus == 1)
        .where(isd.posting_date[filters.from_date : filters.to_date])
        .select(
            isi.purchase_invoice,
            isi.parent.as_("isd_invoice"),
            distributor_gstin.as_("distributor_gstin"),
            recipient_gstin.as_("recipient_gstin"),
            isi.is_ineligible_for_itc,
            *[Sum(getattr(isi, f"distributed_{t}")).as_(f"distributed_{t}") for t in GST_TAX_TYPES],
        )
        .groupby(isi.parent, isi.purchase_invoice, isi.is_ineligible_for_itc)
        .orderby(isi.purchase_invoice)
        .orderby(isi.parent)
    )
    query = _apply_company_filter(query, isd, filters)

    if filters.get("company_gstin"):
        query = query.where(isd.company_gstin == filters.company_gstin)

    purchase_invoices = filters.get("purchase_invoice")
    if purchase_invoices:
        if isinstance(purchase_invoices, str):
            purchase_invoices = [purchase_invoices]
        query = query.where(isi.purchase_invoice.isin(purchase_invoices))

    return query.run(as_dict=True)


def get_distribution_data(filters):
    rows = _get_pi_distribution(filters)
    for row in rows:
        row["is_ineligible_for_itc"] = cint(row.is_ineligible_for_itc)
        row["distributed_total"] = sum(flt(row.get(f"distributed_{t}")) for t in GST_TAX_TYPES)

    return rows


def get_distribution_columns(filters):
    company_currency = get_report_company_currency(filters)

    return [
        {
            "fieldname": "purchase_invoice",
            "label": _("Invoice No"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 200,
        },
        {
            "fieldname": "isd_invoice",
            "label": _("ISD Invoice"),
            "fieldtype": "Link",
            "options": "ISD Invoice",
            "width": 180,
        },
        {
            "fieldname": "distributor_gstin",
            "label": _("Distributor GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "recipient_gstin",
            "label": _("Recipient GSTIN"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "is_ineligible_for_itc",
            "label": _("Ineligible for ITC"),
            "fieldtype": "Check",
            "width": 110,
        },
        {
            "fieldname": "distributed_total",
            "label": _("Total Distributed"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 150,
        },
        {
            "fieldname": "distributed_cgst",
            "label": _("Distributed CGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_sgst",
            "label": _("Distributed SGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_igst",
            "label": _("Distributed IGST"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_cess",
            "label": _("Distributed Cess"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 130,
        },
        {
            "fieldname": "distributed_cess_non_advol",
            "label": _("Distributed Cess (Non-Advol)"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 160,
        },
    ]
