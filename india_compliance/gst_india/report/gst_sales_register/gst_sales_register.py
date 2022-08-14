# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from erpnext.accounts.report.sales_register.sales_register import _execute

from india_compliance.gst_india.constants import (
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
        dict(
            fieldtype="Data",
            label="Billing Address GSTIN",
            fieldname="billing_address_gstin",
            width=140,
        ),
        dict(
            fieldtype="Data",
            label="Company GSTIN",
            fieldname="company_gstin",
            width=120,
        ),
        dict(
            fieldtype="Data",
            label="Place of Supply",
            fieldname="place_of_supply",
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
        "billing_address_gstin",
        "company_gstin",
        "place_of_supply",
        "gst_category",
        "ecommerce_gstin",
    ]

    if reverse_charge_enabled:
        additional_table_columns.insert(3, REVERSE_CHARGE_COLUMNS)
        additional_query_columns.insert(3, "is_reverse_charge")

    if overseas_enabled:
        additional_table_columns.insert(-2, EXPORT_TYPE_COLUMNS)
        additional_query_columns.insert(-2, "is_export_with_gst")

    return _execute(filters, additional_table_columns, additional_query_columns)
