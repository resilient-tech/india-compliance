# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import (
    _execute,
)

from india_compliance.gst_india.report.gst_sales_register.gst_sales_register import (
    ADDITIONAL_QUERY_COLUMNS,
    ADDITIONAL_TABLE_COLUMNS,
    EXPORT_TYPE_COLUMNS,
    REVERSE_CHARGE_COLUMNS,
)


def execute(filters=None):
    overseas_enabled, reverse_charge_enabled = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_overseas_transactions", "enable_reverse_charge_in_sales"),
    )

    additional_table_columns = [
        *ADDITIONAL_TABLE_COLUMNS,
        dict(fieldtype="Data", label="HSN Code", fieldname="gst_hsn_code", width=120),
    ]

    additional_query_columns = [
        *ADDITIONAL_QUERY_COLUMNS,
        "gst_hsn_code",
    ]

    if reverse_charge_enabled:
        additional_table_columns.insert(3, REVERSE_CHARGE_COLUMNS)
        additional_query_columns.insert(3, "is_reverse_charge")

    if overseas_enabled:
        additional_table_columns.insert(-3, EXPORT_TYPE_COLUMNS)
        additional_query_columns.insert(-3, "is_export_with_gst")

    return _execute(filters, additional_table_columns, additional_query_columns)
