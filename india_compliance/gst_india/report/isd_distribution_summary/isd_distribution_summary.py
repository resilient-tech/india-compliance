# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from functools import reduce
from operator import add

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt
from pypika.terms import Case

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils.isd import (
    get_isd_source_item_query,
    get_report_company_currency,
    validate_common_report_filters,
)


def execute(filters=None):
    validate_common_report_filters(filters)
    filters = frappe._dict(filters or {})
    return get_columns(filters), get_data(filters)


def _get_distributed_map(purchase_invoices):
    """Return {(purchase_invoice, is_ineligible_for_itc): distributed_total} for the given purchase invoices."""
    if not purchase_invoices:
        return {}

    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    rows = (
        get_isd_source_item_query(purchase_invoices=purchase_invoices)
        .select(isd_source_item.is_ineligible_for_itc)
        .groupby(isd_source_item.purchase_invoice, isd_source_item.is_ineligible_for_itc)
        .run(as_dict=True)
    )
    return {(r.purchase_invoice, cint(r.is_ineligible_for_itc)): flt(r.total_distributed) for r in rows}


def get_data(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    item_tax = reduce(add, (pi_item[f"{t}_amount"] for t in GST_TAX_TYPES))

    query = (
        frappe.qb.from_(pi)
        .join(pi_item)
        .on(pi_item.parent == pi.name)
        .select(
            pi.company_gstin,
            pi.supplier_gstin,
            pi.name.as_("purchase_invoice"),
            pi.posting_date,
            pi.place_of_supply,
            pi.base_grand_total.as_("total_value"),
            Sum(pi_item.net_amount).as_("taxable_value"),
            Sum(Case().when(pi_item.is_ineligible_for_itc == 0, item_tax).else_(0)).as_("total_eligible_tax"),
            Sum(Case().when(pi_item.is_ineligible_for_itc == 1, item_tax).else_(0)).as_(
                "total_ineligible_tax"
            ),
        )
        .where(pi.docstatus == 1)
        .where(pi.is_isd_applicable == 1)
        .where(pi.posting_date[filters.from_date : filters.to_date])
        .groupby(pi.name)
        .orderby(pi.posting_date)
    )

    if filters.get("company"):
        query = query.where(pi.company == filters.company)
    else:
        permitted = get_permitted_documents("Company")
        if permitted:
            query = query.where(pi.company.isin(permitted))

    if filters.get("company_gstin"):
        query = query.where(pi.company_gstin == filters.company_gstin)

    rows = query.run(as_dict=True)

    dist_map = _get_distributed_map([row.purchase_invoice for row in rows])

    result = []
    for row in rows:
        key1 = (row.purchase_invoice, 0)
        key2 = (row.purchase_invoice, 1)

        eligible_distributed = dist_map.get(key1, 0.0)
        ineligible_distributed = dist_map.get(key2, 0.0)

        total_eligible = flt(row.total_eligible_tax)
        total_ineligible = flt(row.total_ineligible_tax)

        remaining_eligible = total_eligible - eligible_distributed
        remaining_ineligible = total_ineligible - ineligible_distributed

        if filters.get("pending_distribution"):
            if not (remaining_eligible == total_eligible and remaining_ineligible == total_ineligible):
                continue

        result.append(
            {
                "company_gstin": row.company_gstin,
                "supplier_gstin": row.supplier_gstin,
                "purchase_invoice": row.purchase_invoice,
                "posting_date": row.posting_date,
                "place_of_supply": row.place_of_supply,
                "total_value": row.total_value,
                "is_ineligible_for_itc": row.is_ineligible_for_itc,
                "taxable_value": row.taxable_value,
                "total_eligible_tax": total_eligible,
                "total_ineligible_tax": total_ineligible,
                "remaining_eligible_tax": remaining_eligible,
                "remaining_ineligible_tax": remaining_ineligible,
            }
        )

    return result


def get_columns(filters):
    company_currency = get_report_company_currency(filters)

    return [
        {
            "fieldname": "company_gstin",
            "label": _("Company GSTIN"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "supplier_gstin",
            "label": _("Supplier GSTIN"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "purchase_invoice",
            "label": _("Invoice No"),
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 160,
            "sticky": True,
        },
        {
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "place_of_supply",
            "label": _("POS"),
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "total_value",
            "label": _("Total Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
        {
            "fieldname": "is_ineligible_for_itc",
            "label": _("Ineligible for ITC"),
            "fieldtype": "Check",
            "width": 110,
        },
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 120,
        },
        {
            "fieldname": "total_eligible_tax",
            "label": _("Total Eligible Tax"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 140,
        },
        {
            "fieldname": "total_ineligible_tax",
            "label": _("Total Ineligible Tax"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 140,
        },
        {
            "fieldname": "remaining_eligible_tax",
            "label": _("Remaining Eligible Tax"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 160,
        },
        {
            "fieldname": "remaining_ineligible_tax",
            "label": _("Remaining Ineligible Tax"),
            "fieldtype": "Currency",
            "options": company_currency,
            "width": 160,
        },
    ]
