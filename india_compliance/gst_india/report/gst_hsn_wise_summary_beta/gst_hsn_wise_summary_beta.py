# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.query_builder.functions import Date, IfNull, Sum

from india_compliance.gst_india.utils.__init__ import get_gst_uom

DOCTYPE_MAP = {
    "Inward": ["Purchase Invoice", "Bill of Entry"],
    "Outward": ["Sales Invoice"],
}


def execute(filters=None):
    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def validate_filters(filters):
    filters = frappe._dict(filters)

    if filters.from_date > filters.to_date:
        frappe.throw(_("To Date cannot be less than From Date"))


def get_data(filters):
    doctype_list = DOCTYPE_MAP[filters.type_of_supplies]
    query_list = []

    for doctype in doctype_list:
        query = get_transaction_data_query(doctype, filters)
        query_list.append(query)

    data = get_summary_data(query_list)

    return get_merged_data(data)


def get_merged_data(data):
    merged_hsn_dict = {}
    amount_fields = {
        "total_qty": 0,
        "tax_rate": 0,
        "total_value": 0,
        "total_taxable_value": 0,
        "total_igst_amount": 0,
        "total_cgst_amount": 0,
        "total_sgst_amount": 0,
        "total_cess_amount": 0,
    }

    for row in data:
        if row.gst_hsn_code.startswith("99"):
            # service item doesn't have qty/uom
            row.total_qty = 0
            row.gst_uom = "NA"
        else:
            row.gst_uom = get_gst_uom(row.get("uom"))

        key = f"{row['gst_hsn_code']}-{row['gst_uom']}-{row['tax_rate']}"

        new_row = merged_hsn_dict.setdefault(key, {**row, **amount_fields})

        for key in amount_fields:
            new_row[key] += row[key]

    return list(merged_hsn_dict.values())


def get_transaction_data_query(doctype, filters):
    invoice = frappe.qb.DocType(doctype)
    invoice_item = frappe.qb.DocType(f"{doctype} Item")
    hsn_code = frappe.qb.DocType("GST HSN Code")

    query = (
        frappe.qb.from_(invoice_item)
        .join(invoice)
        .on(invoice.name == invoice_item.parent)
        .left_join(hsn_code)
        .on(invoice_item.gst_hsn_code == hsn_code.hsn_code)
        .select(
            invoice_item.gst_hsn_code.as_("gst_hsn_code"),
            IfNull(hsn_code.description, "").as_("description"),
            invoice_item.uom.as_("uom"),
            invoice_item.qty,
            (
                invoice_item.cgst_rate + invoice_item.sgst_rate + invoice_item.igst_rate
            ).as_("tax_rate"),
            invoice_item.igst_amount,
            invoice_item.cgst_amount,
            invoice_item.sgst_amount,
            invoice_item.taxable_value.as_("taxable_amount"),
            (invoice_item.cess_amount + invoice_item.cess_non_advol_amount).as_(
                "cess_amount"
            ),
        )
        .where(Date(invoice.posting_date).between(filters.from_date, filters.to_date))
        .where(IfNull(invoice_item.gst_hsn_code, "") != "")
        .where(invoice.company == filters.company)
        .where(invoice.docstatus == 1)
    )

    if doctype != "Bill of Entry":
        query = query.where(invoice.is_opening != "Yes")

    if doctype == "Purchase Invoice":
        query = query.where(
            (invoice.gst_category != "Overseas") & (invoice.is_reverse_charge != 1)
        )

    if filters.get("compnay_gstin"):
        query = query.where(IfNull(invoice.company_gstin, "") == filters.company_gstin)

    if filters.get("gst_hsn_code"):
        query = query.where(
            IfNull(invoice_item.gst_hsn_code, "") == filters.gst_hsn_code
        )

    return query


def get_summary_data(query_list):
    query = query_list[0]

    for qlist in query_list[1:]:
        query = query * qlist

    data = (
        frappe.qb.from_(query)
        .select(
            query.gst_hsn_code.as_("gst_hsn_code"),
            query.description,
            query.uom,
            Sum(query.qty).as_("total_qty"),
            query.tax_rate,
            Sum(
                query.igst_amount
                + query.cgst_amount
                + query.sgst_amount
                + query.taxable_amount
                + query.cess_amount
            ).as_("total_value"),
            Sum(query.taxable_amount).as_("total_taxable_value"),
            Sum(query.igst_amount).as_("total_igst_amount"),
            Sum(query.cgst_amount).as_("total_cgst_amount"),
            Sum(query.sgst_amount).as_("total_sgst_amount"),
            Sum(query.cess_amount).as_("total_cess_amount"),
        )
        .groupby(
            query.gst_hsn_code,
            query.uom,
            query.tax_rate,
        )
    )

    return data.run(as_dict=True)


def get_columns(filters=None):
    columns = [
        {
            "fieldname": "gst_hsn_code",
            "label": _("HSN"),
            "fieldtype": "Link",
            "options": "GST HSN Code",
            "width": 100,
        },
        {
            "fieldname": "description",
            "label": _("Description"),
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "fieldname": "gst_uom",
            "label": _("UQC"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "total_qty",
            "label": _("Total Qty"),
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "total_value",
            "label": _("Total Value"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "tax_rate",
            "label": _("Rate"),
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "total_taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "total_igst_amount",
            "label": _("Integrated Tax Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "total_cgst_amount",
            "label": _("Central Tax Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "total_sgst_amount",
            "label": _("State/UT Tax Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "total_cess_amount",
            "label": _("CESS Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
    ]

    return columns
