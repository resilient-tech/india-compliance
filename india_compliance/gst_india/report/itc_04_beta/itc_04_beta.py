# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
from frappe import _

from india_compliance.gst_india.utils.itc_04.itc_04_data import ITC04Query


def execute(filters=None):
    if not filters:
        filters = {}

    _class = ITC04Query(filters)
    data = []

    if filters.category == "Table 4":
        columns = get_columns_table_4()
        data = _class.get_query_table_4_se().run(as_dict=True)
        data.extend(_class.get_query_table_4_sr().run(as_dict=True))
    else:
        columns = get_columns_table_5A()
        data = _class.get_query_table_5A_se().run(as_dict=True)
        data.extend(_class.get_query_table_5A_sr().run(as_dict=True))

    return columns, data


def get_common_columns():
    return [
        {
            "fieldname": "company_gstin",
            "label": _("Company GSTIN"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "posting_date",
            "label": _("Posting Date"),
            "fieldtype": "Date",
            "width": 180,
        },
        {
            "fieldname": "invoice_type",
            "label": _("Invoice Type"),
            "width": 180,
        },
        {
            "fieldname": "supplier",
            "label": _("Supplier"),
            "fieldtype": "Link",
            "options": "Supplier",
            "width": 180,
        },
        {
            "fieldname": "gst_category",
            "label": _("GST Category"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "supplier_gstin",
            "label": _("Supplier GSTIN"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "place_of_supply",
            "label": _("Destination of Supply"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "is_return",
            "label": _("Is Return"),
            "fieldtype": "Check",
            "width": 180,
        },
        {
            "fieldname": "item_code",
            "label": _("Item Code"),
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
        {
            "fieldname": "gst_hsn_code",
            "label": _("HSN Code"),
            "fieldtype": "Link",
            "options": "GST HSN Code",
            "width": 120,
        },
        {
            "fieldname": "uom",
            "label": _("UOM"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "gst_treatment",
            "label": _("GST Treatment"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "qty",
            "label": _("Qty"),
            "fieldtype": "Float",
            "width": 180,
        },
        {
            "fieldname": "item_type",
            "label": _("Item Type (Input/Capital Goods)"),
            "fieldtype": "Data",
            "width": 180,
        },
    ]


def get_columns_table_4():
    return get_common_columns() + [
        {
            "fieldname": "invoice_no",
            "label": _("Invoice No (Challan No)"),
            "fieldtype": "Dynamic Link",
            "options": "invoice_type",
            "width": 180,
        },
        {
            "fieldname": "taxable_value",
            "label": _("Taxable Value"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "gst_rate",
            "label": _("GST Rate"),
            "fieldtype": "Percent",
            "width": 180,
        },
        {
            "fieldname": "cgst_amount",
            "label": _("CGST Amount"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "sgst_amount",
            "label": _("SGST Amount"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "igst_amount",
            "label": _("IGST Amount"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "total_cess_amount",
            "label": _("Total Cess Amount"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "total_tax",
            "label": _("Total Tax"),
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "total_amount",
            "label": _("Total Amount"),
            "fieldtype": "Currency",
            "width": 180,
        },
    ]


def get_columns_table_5A():
    return [
        {
            "fieldname": "original_challan_no",
            "label": _("Original Challan No"),
            "fieldtype": "Dynamic Link",
            "options": "original_challan_invoice_type",
            "width": 180,
        },
        {
            "fieldname": "invoice_no",
            "label": _("Job Worker Invoice No (Challan No)"),
            "fieldtype": "Dynamic Link",
            "options": "invoice_type",
            "width": 180,
        },
    ] + get_common_columns()
