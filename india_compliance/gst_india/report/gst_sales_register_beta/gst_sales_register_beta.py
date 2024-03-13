# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import getdate


def execute(filters=None):
    if not filters:
        return [], []

    filters = frappe._dict(filters)
    columns = get_columns(filters)
    data = []

    if filters.summary_by == "Summary by Item":
        data = get_data_for_item_wise_summary(filters)
    elif filters.summary_by == "Summary by HSN":
        data = get_data_for_hsn_wise_summary(filters)

    return columns, data


def get_columns(filters):
    columns = []

    if not filters.company_gstin:
        columns.append(
            {
                "label": _("Company GSTIN"),
                "fieldname": "company_gstin",
                "width": 120,
            },
        )

    columns.extend(
        [
            {
                "label": _("Posting Date"),
                "fieldname": "posting_date",
                "width": 120,
            },
            {
                "label": _("Invoice Number"),
                "fieldname": "invoice_no",
                "fieldtype": "Link",
                "options": "Sales Invoice",
                "width": 120,
            },
            {
                "label": _("Customer Name"),
                "fieldname": "customer_name",
                "fieldtype": "Link",
                "options": "Customer",
                "width": 120,
            },
            {
                "label": _("GST Category"),
                "fieldname": "gst_category",
                "width": 120,
            },
            {
                "label": _("Billing Address GSTIN"),
                "fieldname": "billing_address_gstin",
                "width": 120,
            },
            {
                "label": _("Place of Supply"),
                "fieldname": "place_of_supply",
                "width": 120,
            },
        ]
    )

    gst_settings = frappe.get_doc("GST Settings")

    if gst_settings.enable_reverse_charge_in_sales:
        columns.append(
            {
                "label": _("Is Reverse Charge"),
                "fieldname": "is_reverse_charge",
                "fieldtype": "Check",
                "width": 60,
            }
        )

    if gst_settings.enable_overseas_transactions:
        columns.append(
            {
                "label": _("Is Export with GST"),
                "fieldname": "is_export_with_gst",
                "fieldtype": "Check",
                "width": 60,
            }
        )

    columns.extend(
        [
            {
                "label": _("Is Return"),
                "fieldname": "is_return",
                "fieldtype": "Check",
                "width": 60,
            },
            {
                "label": _("Is Rate Adjustment Entry"),
                "fieldname": "is_debit_note",
                "fieldtype": "Check",
                "width": 60,
            },
        ]
    )

    if filters.summary_by == "Summary by Item":
        columns.append(
            {
                "label": _("Item Code"),
                "fieldname": "item",
                "fieldtype": "Link",
                "options": "Item",
                "width": 120,
            }
        )

    columns.extend(
        [
            {
                "label": _("HSN Code"),
                "fieldname": "gst_hsn_code",
                "fieldtype": "Link",
                "options": "GST HSN Code",
                "width": 120,
            },
            {"label": _("Taxable Value"), "fieldname": "taxable_value", "width": 120},
            {"label": _("GST Treatment"), "fieldname": "gst_treatment", "width": 120},
            {"label": _("GST Rate"), "fieldname": "gst_rate", "width": 60},
            {"label": _("CGST Amount"), "fieldname": "cgst_amount", "width": 120},
            {"label": _("SGST Amount"), "fieldname": "sgst_amount", "width": 120},
            {"label": _("IGST Amount"), "fieldname": "igst_amount", "width": 120},
            {"label": _("Cess Amount"), "fieldname": "cess_amount", "width": 120},
            {"label": _("Total Tax"), "fieldname": "total_tax", "width": 120},
            {"label": _("Total Amount"), "fieldname": "total_amount", "width": 120},
        ]
    )

    return columns


def get_data_for_item_wise_summary(filters=None):
    si = frappe.qb.DocType("Sales Invoice")
    si_item = frappe.qb.DocType("Sales Invoice Item")

    query = get_base_query(si, si_item)
    query = query.select(si_item.item_code.as_("item"))
    query = get_query_with_filters(si, query, filters)

    return query.run(as_dict=True)


def get_data_for_hsn_wise_summary(filters):
    si = frappe.qb.DocType("Sales Invoice")
    si_item = frappe.qb.DocType("Sales Invoice Item")

    query = get_base_query(si, si_item)
    query = query.select(
        Sum(si_item.taxable_value).as_("taxable_value"),
        Sum(si_item.cgst_amount).as_("cgst_amount"),
        Sum(si_item.sgst_amount).as_("sgst_amount"),
        Sum(si_item.igst_amount).as_("igst_amount"),
        Sum(si_item.cess_amount).as_("cess_amount"),
    ).groupby(
        si.name,
        si_item.gst_hsn_code,
        (si_item.cgst_rate + si_item.sgst_rate + si_item.igst_rate),
        si_item.gst_treatment,
    )
    query = get_query_with_filters(si, query, filters)

    return query.run(as_dict=True)


def get_base_query(si, si_item):
    query = (
        frappe.qb.from_(si)
        .inner_join(si_item)
        .on(si.name == si_item.parent)
        .select(
            si_item.gst_hsn_code,
            si.billing_address_gstin,
            si.company_gstin,
            si.customer_name,
            si.name.as_("invoice_no"),
            si.posting_date,
            si.place_of_supply,
            si.is_reverse_charge,
            si.is_export_with_gst,
            si.is_return,
            si.is_debit_note,
            si.gst_category,
            si_item.gst_treatment,
            (si_item.cgst_rate + si_item.sgst_rate + si_item.igst_rate).as_("gst_rate"),
            (si_item.cgst_amount + si_item.sgst_amount + si_item.igst_amount).as_(
                "total_tax"
            ),
            (
                si_item.taxable_value
                + si_item.cgst_amount
                + si_item.sgst_amount
                + si_item.igst_amount
                + si_item.cess_amount
            ).as_("total_amount"),
        )
        .where(si.docstatus == 1)
    )

    return query


def get_query_with_filters(si, query, filters=None):
    if filters.company:
        query = query.where(si.company == filters.company)

    if filters.company_gstin:
        query = query.where(si.company_gstin == filters.company_gstin)

    if filters.from_date:
        query = query.where(si.posting_date >= getdate(filters.from_date))

    if filters.to_date:
        query = query.where(si.posting_date <= getdate(filters.to_date))

    return query
