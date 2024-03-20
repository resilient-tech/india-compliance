# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.query_builder.functions import Date, IfNull, Sum
from india_compliance.gst_india.utils.__init__ import get_gst_uom


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

    purchase_invoice_data = get_invoice_data("Purchase Invoice", filters)
    boe_data = get_invoice_data("Bill of Entry", filters)
    data =  get_inward_data(purchase_invoice_data, boe_data)
    return data
    # for item in data:
    #     item["gst_uom"] = get_gst_uom(item.get("uom"))
    # return data


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
            IfNull(hsn_code.description, "").as_("description"),
            # invoice_item.stock_uom.as_("uom"),
            # invoice_item.stock_qty,
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

    if doctype == "Purchase Invoice":
        query = query.where(invoice.is_opening != "Yes")

    if filters.get("compnay_gstin"):
        query = query.where(IfNull(invoice.company_gstin, "") == filters.company_gstin)

    if filters.get("gst_hsn_code"):
        query = query.where(
            IfNull(invoice_item.gst_hsn_code, "") == filters.gst_hsn_code
        )

    return query


def get_inward_data(purchase_invoice_data, boe_data):

    query = purchase_invoice_data * boe_data

    data = (
        frappe.qb.from_(query)
        .select(
            query.gst_hsn_code.as_("gst_hsn_code"),
            query.description,
            # Sum(query.uom).as_("uom"),
            # Sum(query.stock_qty).as_("stock_qty"),
            query.tax_rate.as_("tax_rate"),
            Sum(
                query.igst_amount
                + query.cgst_amount
                + query.sgst_amount
                + query.taxable_amount
                + query.cess_amount
            ).as_("total_amount"),
            Sum(query.taxable_amount).as_("taxable_amount"),
            Sum(query.igst_amount).as_("igst_amount"),
            Sum(query.cgst_amount).as_("cgst_amount"),
            Sum(query.sgst_amount).as_("sgst_amount"),
            Sum(query.cess_amount).as_("cess_amount"),
        )
        .groupby(
            query.gst_hsn_code,
            # query.uom
            query.tax_rate,
        )
    )
    return data.run(as_dict=True)


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
            "fieldname": "uom",
            "label": _("UOM"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "gst_uom",
            "label": _("GST UOM"),
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
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("Total SGST Amount"),
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("Total CGST Amount"),
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "fieldname": "cess_amount",
            "label": _("Total CESS Amount"),
            "fieldtype": "Float",
            "width": 120,
        },
    ]

    return columns
