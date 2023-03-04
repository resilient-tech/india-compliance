# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from erpnext.accounts.report.sales_register.sales_register import _execute

EXPORT_TYPE_COLUMN = {
    "fieldtype": "Check",
    "label": _("Is Export With GST"),
    "fieldname": "is_export_with_gst",
    "width": 120,
}

REVERSE_CHARGE_COLUMN = {
    "fieldtype": "Check",
    "label": _("Is Reverse Charge"),
    "fieldname": "is_reverse_charge",
    "width": 120,
}

ADDITIONAL_TABLE_COLUMNS = [
    {
        "fieldtype": "Data",
        "label": _("Billing Address GSTIN"),
        "fieldname": "billing_address_gstin",
        "width": 140,
    },
    {
        "fieldtype": "Data",
        "label": _("Company GSTIN"),
        "fieldname": "company_gstin",
        "width": 120,
    },
    {
        "fieldtype": "Data",
        "label": _("Place of Supply"),
        "fieldname": "place_of_supply",
        "width": 120,
    },
    {
        "fieldtype": "Data",
        "label": _("GST Category"),
        "fieldname": "gst_category",
        "width": 120,
    },
    {
        "fieldtype": "Data",
        "label": _("E-Commerce GSTIN"),
        "fieldname": "ecommerce_gstin",
        "width": 130,
    },
]


def get_additional_table_columns():
    overseas_enabled, reverse_charge_enabled = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_overseas_transactions", "enable_reverse_charge_in_sales"),
    )

    additional_table_columns = ADDITIONAL_TABLE_COLUMNS.copy()

    if reverse_charge_enabled:
        additional_table_columns.insert(-2, REVERSE_CHARGE_COLUMN)

    if overseas_enabled:
        additional_table_columns.insert(-2, EXPORT_TYPE_COLUMN)

    return additional_table_columns


def get_column_names(additional_table_columns):
    return [column["fieldname"] for column in additional_table_columns]


def execute(filters=None):
    additional_table_columns = get_additional_table_columns()

    return _execute(
        filters,
        additional_table_columns,
        get_column_names(additional_table_columns),
    )
