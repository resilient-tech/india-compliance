# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
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
            "label": "Company GSTIN",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "posting_date",
            "label": "Posting Date",
            "fieldtype": "Date",
            "width": 180,
        },
        {
            "fieldname": "invoice_no",
            "label": "Invoice No (Challan No)",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "supplier",
            "label": "Supplier",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "gst_category",
            "label": "GST Category",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "supplier_gstin",
            "label": "Supplier GSTIN",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "place_of_supply",
            "label": "Destination of Supply",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "is_return",
            "label": "Is Return",
            "fieldtype": "Check",
            "width": 180,
        },
        {
            "fieldname": "item_code",
            "label": "Item Code",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "gst_hsn_code",
            "label": "HSN Code",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "uom",
            "label": "UOM",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "gst_treatment",
            "label": "GST Treatment",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "qty",
            "label": "Qty",
            "fieldtype": "Float",
            "width": 180,
        },
        {
            "fieldname": "item_type",
            "label": "Item Type (Input/Capital Goods)",
            "fieldtype": "Data",
            "width": 180,
        },
    ]


def get_columns_table_4():
    return get_common_columns() + [
        {
            "fieldname": "taxable_value",
            "label": "Taxable Value",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "gst_rate",
            "label": "GST Rate",
            "fieldtype": "Percent",
            "width": 180,
        },
        {
            "fieldname": "cgst_amount",
            "label": "CGST Amount",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "sgst_amount",
            "label": "SGST Amount",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "igst_amount",
            "label": "IGST Amount",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "total_cess_amount",
            "label": "Total Cess Amount",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "total_tax",
            "label": "Total Tax",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "fieldname": "total_amount",
            "label": "Total Amount",
            "fieldtype": "Currency",
            "width": 180,
        },
    ]


def get_columns_table_5A():
    return [
        {
            "fieldname": "original_challan_no",
            "label": "Original Challan No",
            "fieldtype": "Data",
            "width": 180,
        },
    ] + get_common_columns()
