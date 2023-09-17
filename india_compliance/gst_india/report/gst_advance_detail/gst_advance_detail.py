# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

# import frappe


def execute(filters=None):
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {
            "fieldname": "posting_date",
            "label": "Posting Date",
            "fieldtype": "Date",
            "width": 120,
        },
        {
            "fieldname": "payment_entry",
            "label": "Payment Entry",
            "fieldtype": "Link",
            "options": "Payment Entry",
            "width": 120,
        },
        {
            "fieldname": "Customer",
            "label": "Customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 150,
        },
        {
            "fieldname": "Customer Name",
            "label": "Customer Name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "paid_amount",
            "label": "Paid Amount",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "gst_paid",
            "label": "GST Paid",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "gst_utilized",
            "label": "GST Utilized",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "place_of_supply",
            "label": "Place of Supply",
            "fieldtype": "Data",
            "width": 150,
        },
    ]


def get_data(filters):
    return [["a", "b", "c", "d", "e", "f", "g", "h", "i"]]
