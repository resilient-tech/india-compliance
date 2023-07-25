# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe import _
from erpnext.accounts.report.purchase_register.purchase_register import _execute
import frappe


def execute(filters=None):
    data=_execute(filters, get_additional_table_columns())
    data_internal = remove_internal_supplier_data(data)
    return data[0],data_internal



def get_additional_table_columns():
    return [
        {
            "fieldtype": "Data",
            "label": _("Supplier GSTIN"),
            "fieldname": "supplier_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("Company GSTIN"),
            "fieldname": "company_gstin",
            "width": 120,
        },
        {
            "fieldtype": "Check",
            "label": _("Is Reverse Charge"),
            "fieldname": "is_reverse_charge",
            "width": 120,
        },
        {
            "fieldtype": "Data",
            "label": _("GST Category"),
            "fieldname": "gst_category",
            "width": 120,
        },
    ]


def remove_internal_supplier_data(data):
    new_data=[]
    for row in data[1]:
        if not frappe.get_cached_value(
            "Supplier", row[2], "is_internal_supplier"
        ):
            new_data.append(row)
    return new_data

