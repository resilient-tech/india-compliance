# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.query_builder.functions import Sum
from frappe.utils import flt
from pypika.terms import Case


def execute(filters=None):
    validate_filters(filters)
    filters = frappe._dict(filters or {})
    return get_columns(filters), get_data(filters)


def validate_filters(filters=None):
    if not filters:
        filters = {}
    filters = frappe._dict(filters)

    if filters.company:
        frappe.has_permission("Company", doc=filters.company, throw=True)

    if not filters.from_date or not filters.to_date:
        frappe.throw(
            _("From Date & To Date is mandatory for generating ISD Distribution Summary"),
            title=_("Invalid Filter"),
        )
    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date must be before To Date"), title=_("Invalid Filter"))


def _dist_tax_sum(table):
    """Sum of distributed tax fields on ISD Invoice Source Item."""
    return (
        table.distributed_igst
        + table.distributed_cgst
        + table.distributed_sgst
        + table.distributed_cess
        + table.distributed_cess_non_advol
    )


def _get_distributed_map():
    """Return {(purchase_invoice, is_ineligible_for_itc): distributed_total} for all submitted ISD invoices."""
    isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
    isd_invoice = frappe.qb.DocType("ISD Invoice")

    rows = (
        frappe.qb.from_(isd_source_item)
        .join(isd_invoice)
        .on(isd_source_item.parent == isd_invoice.name)
        .select(
            isd_source_item.purchase_invoice,
            isd_source_item.is_ineligible_for_itc,
            Sum(_dist_tax_sum(isd_source_item)).as_("distributed_total"),
        )
        .where(isd_invoice.docstatus == 1)
        .groupby(isd_source_item.purchase_invoice, isd_source_item.is_ineligible_for_itc)
        .run(as_dict=True)
    )

    return {(r.purchase_invoice, r.is_ineligible_for_itc): flt(r.distributed_total) for r in rows}


def get_data(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    item_tax = (
        pi_item.igst_amount
        + pi_item.cgst_amount
        + pi_item.sgst_amount
        + pi_item.cess_amount
        + pi_item.cess_non_advol_amount
    )

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
            Sum(
                Case()
                .when(pi_item.is_ineligible_for_itc == 0, item_tax)
                .else_(0)
            ).as_("total_eligible_tax"),
            Sum(
                Case()
                .when(pi_item.is_ineligible_for_itc == 1, item_tax)
                .else_(0)
            ).as_("total_ineligible_tax"),
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

    dist_map = _get_distributed_map()

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
    company_currency = (
        frappe.get_cached_value("Company", filters.company, "default_currency")
        if filters.get("company")
        else frappe.db.get_default("currency") or "INR"
    )

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
