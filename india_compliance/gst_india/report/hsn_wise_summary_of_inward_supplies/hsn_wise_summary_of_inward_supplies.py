# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.query_builder.functions import Sum


def execute(filters=None):

    validate_filters(filters)

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def validate_filters(filters=None):
    filters = frappe._dict(filters or {})

    if filters.from_date > filters.to_date:
        frappe.throw(_("To Date cannot be less than From Date"))


def get_data(filters=None):
    purchase_invoice = frappe.qb.DocType("Purchase Invoice")
    purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")
    hsn_code = frappe.qb.DocType("GST HSN Code")

    query = (
        frappe.qb.from_(purchase_invoice_item)
        .join(purchase_invoice)
        .on(purchase_invoice.name == purchase_invoice_item.parent)
        .join(hsn_code)
        .on(purchase_invoice_item.gst_hsn_code == hsn_code.hsn_code)
        .select(
            purchase_invoice_item.gst_hsn_code.as_("gst_hsn_code"),
            hsn_code.description,
            purchase_invoice_item.stock_uom.as_("uqc"),
            purchase_invoice_item.stock_qty,
            (
                purchase_invoice_item.cgst_rate
                + purchase_invoice_item.sgst_rate
                + purchase_invoice_item.igst_rate
            ).as_("tax_rate"),
            Sum(purchase_invoice_item.igst_amount).as_("igst_amount"),
            Sum(purchase_invoice_item.cgst_amount).as_("cgst_amount"),
            Sum(purchase_invoice_item.sgst_amount).as_("sgst_amount"),
            Sum(
                purchase_invoice_item.igst_amount
                + purchase_invoice_item.cgst_amount
                + purchase_invoice_item.sgst_amount
                + purchase_invoice_item.taxable_value
            ).as_("total_amount"),
            Sum(purchase_invoice_item.taxable_value).as_("taxable_amount"),
        )
        # .where    gstin field condition
        .where(purchase_invoice.creation.between(filters.from_date, filters.to_date))
        .groupby(
            purchase_invoice_item.gst_hsn_code,
            purchase_invoice_item.stock_uom,
            purchase_invoice_item.cgst_rate
            + purchase_invoice_item.sgst_rate
            + purchase_invoice_item.igst_rate,
        )
    )
    return query.run(as_dict=True)


def get_columns(filters=None):
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
