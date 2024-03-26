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

    if filters.from_date and filters.to_date:
        if getdate(filters.from_date) > getdate(filters.to_date):
            frappe.throw(_("The end date cannot precede the start date"))

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
                "options": "Purchase Invoice",
                "width": 150,
            },
            {
                "label": _("Bill Number"),
                "fieldname": "bill_no",
                "width": 120,
            },
            {
                "label": _("Bill Date"),
                "fieldname": "bill_date",
                "width": 120,
            },
            {
                "label": _("Supplier Name"),
                "fieldname": "supplier",
                "fieldtype": "Link",
                "options": "Supplier",
                "width": 150,
            },
            {
                "label": _("GST Category"),
                "fieldname": "gst_category",
                "width": 120,
            },
            {
                "label": _("Supplier GSTIN"),
                "fieldname": "supplier_gstin",
                "width": 180,
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
                "width": 120,
            }
        )

    columns.extend(
        [
            {
                "label": _("Is Return"),
                "fieldname": "is_return",
                "fieldtype": "Check",
                "width": 60,
            }
        ]
    )

    if filters.summary_by == "Summary by Item":
        columns.extend(
            [
                {
                    "label": _("Item Code"),
                    "fieldname": "item",
                    "fieldtype": "Link",
                    "options": "Item",
                    "width": 180,
                },
                {
                    "label": _("Is Ineligible for ITC"),
                    "fieldname": "is_ineligible_for_itc",
                    "fieldtype": "Check",
                    "width": 120,
                },
            ]
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
            {
                "label": _("Total Cess Amount"),
                "fieldname": "total_cess_amount",
                "width": 120,
            },
            {"label": _("Total Tax"), "fieldname": "total_tax", "width": 120},
            {"label": _("Total Amount"), "fieldname": "total_amount", "width": 120},
        ]
    )

    return columns


def get_data_for_item_wise_summary(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    query = get_base_query(pi, pi_item)
    query = query.select(
        pi_item.item_code.as_("item"),
        pi_item.taxable_value,
        pi_item.cgst_amount,
        pi_item.sgst_amount,
        pi_item.igst_amount,
        (pi_item.cess_amount + pi_item.cess_non_advol_amount).as_("total_cess_amount"),
        (pi_item.cgst_amount + pi_item.sgst_amount + pi_item.igst_amount).as_(
            "total_tax"
        ),
        (
            pi_item.taxable_value
            + pi_item.cgst_amount
            + pi_item.sgst_amount
            + pi_item.igst_amount
            + pi_item.cess_amount
            + pi_item.cess_non_advol_amount
        ).as_("total_amount"),
    )
    query = get_query_with_filters(pi, query, filters)

    return query.run(as_dict=True)


def get_data_for_hsn_wise_summary(filters):
    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    query = get_base_query(pi, pi_item)
    query = query.select(
        Sum(pi_item.taxable_value).as_("taxable_value"),
        Sum(pi_item.cgst_amount).as_("cgst_amount"),
        Sum(pi_item.sgst_amount).as_("sgst_amount"),
        Sum(pi_item.igst_amount).as_("igst_amount"),
        (Sum(pi_item.cess_amount) + Sum(pi_item.cess_non_advol_amount)).as_(
            "total_cess_amount"
        ),
        (
            Sum(pi_item.cgst_amount)
            + Sum(pi_item.sgst_amount)
            + Sum(pi_item.igst_amount)
        ).as_("total_tax"),
        (
            Sum(pi_item.taxable_value)
            + Sum(pi_item.cgst_amount)
            + Sum(pi_item.sgst_amount)
            + Sum(pi_item.igst_amount)
            + Sum(pi_item.cess_amount)
            + Sum(pi_item.cess_non_advol_amount)
        ).as_("total_amount"),
    ).groupby(
        pi.name,
        pi_item.gst_hsn_code,
        (pi_item.cgst_rate + pi_item.sgst_rate + pi_item.igst_rate),
        pi_item.gst_treatment,
    )
    query = get_query_with_filters(pi, query, filters)

    return query.run(as_dict=True)


def get_base_query(pi, pi_item):

    query = (
        frappe.qb.from_(pi)
        .inner_join(pi_item)
        .on(pi.name == pi_item.parent)
        .select(
            pi_item.gst_hsn_code,
            pi.supplier_gstin,
            pi.company_gstin,
            pi.supplier,
            pi.name.as_("invoice_no"),
            pi.posting_date,
            pi.bill_no,
            pi.bill_date,
            pi.place_of_supply,
            pi.is_reverse_charge,
            pi.is_return,
            pi.gst_category,
            pi_item.gst_treatment,
            (pi_item.cgst_rate + pi_item.sgst_rate + pi_item.igst_rate).as_("gst_rate"),
        )
        .where(pi.docstatus == 1)
        .where(pi.is_opening != "Yes")
    )

    return query


def get_query_with_filters(pi, query, filters=None):
    if filters.company:
        query = query.where(pi.company == filters.company)

    if filters.company_gstin:
        query = query.where(pi.company_gstin == filters.company_gstin)

    if filters.from_date:
        query = query.where(pi.posting_date >= getdate(filters.from_date))

    if filters.to_date:
        query = query.where(pi.posting_date <= getdate(filters.to_date))

    return query
