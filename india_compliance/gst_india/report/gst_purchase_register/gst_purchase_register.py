# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.report.purchase_register.purchase_register import _execute

from india_compliance.gst_india.constants import (
    EXPORT_TYPE_COLUMNS,
    REVERSE_CHARGE_COLUMNS,
)

overseas_enabled, reverse_charge_enabled = frappe.get_cached_value(
    "GST Settings",
    "GST Settings",
    ("enable_overseas_transactions", "enable_reverse_charge_in_sales"),
)


def execute(filters=None):
    additional_table_columns = [
        dict(
            fieldtype="Data",
            label="Supplier GSTIN",
            fieldname="supplier_gstin",
            width=120,
        ),
        dict(
            fieldtype="Data",
            label="Company GSTIN",
            fieldname="company_gstin",
            width=120,
        ),
        dict(
            fieldtype="Data",
            label="GST Category",
            fieldname="gst_category",
            width=120,
        ),
        dict(
            fieldtype="Data",
            label="E-Commerce GSTIN",
            fieldname="ecommerce_gstin",
            width=130,
        ),
    ]
    additional_query_columns = [
        "supplier_gstin",
        "company_gstin",
        "gst_category",
        "ecommerce_gstin",
    ]

    if reverse_charge_enabled:
        additional_table_columns.append(REVERSE_CHARGE_COLUMNS)
        additional_query_columns.append("is_reverse_charge")

    if overseas_enabled:
        additional_table_columns.append(EXPORT_TYPE_COLUMNS)
        additional_query_columns.append("is_export_with_gst")

    return _execute(filters, additional_table_columns, additional_query_columns)
