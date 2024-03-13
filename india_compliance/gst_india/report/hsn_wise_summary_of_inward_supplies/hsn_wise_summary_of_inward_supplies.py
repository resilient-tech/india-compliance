# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.query_builder.functions import Date, Sum, IfNull


def execute(filters=None):
    validate_filters(filters)

    columns = get_columns(filters)
    data = get_invoice_data(filters)

    return columns, data


def validate_filters(filters):
    filters = frappe._dict(filters)

    if filters.from_date > filters.to_date:
        frappe.throw(_("To Date cannot be less than From Date"))


def get_data(filters):
    data = []

    purchase_invoice_data = get_invoice_data("Purchase Invoice", filters)
    boe_data = get_invoice_data("Purchase Invoice", filters)

    data = purchase_invoice_data + boe_data

    return data


def get_invoice_data(doctype, filters):
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
            IfNull(hsn_code.description, "").as_("hsn_code.description"),
            invoice_item.stock_uom.as_("uqc"),
            invoice_item.stock_qty,
            (
                invoice_item.cgst_rate + invoice_item.sgst_rate + invoice_item.igst_rate
            ).as_("tax_rate"),
            Sum(invoice_item.igst_amount).as_("igst_amount"),
            Sum(invoice_item.cgst_amount).as_("cgst_amount"),
            Sum(invoice_item.sgst_amount).as_("sgst_amount"),
            Sum(invoice_item.taxable_value).as_("taxable_amount"),
            Sum(
                invoice_item.igst_amount
                + invoice_item.cgst_amount
                + invoice_item.sgst_amount
                + invoice_item.taxable_value
            ).as_("total_amount"),
        )
        .where(
            Date(invoice.posting_date).between(filters.from_date, filters.to_date),
            IfNull(invoice_item.gst_hsn_code, "") != "",
            invoice.company == filters.company,
            invoice.docstatus == 1,
            invoice.is_opening != "Yes",
        )
        .groupby(
            invoice_item.gst_hsn_code,
            invoice_item.stock_uom,
            invoice_item.cgst_rate + invoice_item.sgst_rate + invoice_item.igst_rate,
        )
    )

    if filters.get("compnay_gstin"):
        query = query.where(IfNull(invoice.company_gstin, "") == filters.company_gstin)

    if filters.get("gst_hsn_code"):
        query = query.where(
            IfNull(invoice_item.gst_hsn_code, "") == filters.gst_hsn_code
        )
        
    return query.run(as_dict=True)


def get_columns(filters):
    columns = [
        {
            "fieldname": "gst_hsn_code",
            "label": _("HSN/SAC"),
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
            "fieldname": "uqc",
            "label": _("UQC"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "stock_qty",
            "label": _("Stock Qty"),
            "fieldtype": "Float",
            "width": 90,
        },
        {
            "fieldname": "tax_rate",
            "label": _("Tax Rate"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "total_amount",
            "label": _("Total Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 120,
        },
        {
            "fieldname": "taxable_amount",
            "label": _("Total Taxable Amount"),
            "fieldtype": "Currency",
            "options": "Company:company:default_currency",
            "width": 170,
        },
        {
            "fieldname": "igst_amount",
            "label": _("Total IGST Amount"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("Total SGST Amount"),
            "fieldtype": "Int",
            "width": 120,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("Total CGST Amount"),
            "fieldtype": "Int",
            "width": 120,
        },
    ]

    return columns
