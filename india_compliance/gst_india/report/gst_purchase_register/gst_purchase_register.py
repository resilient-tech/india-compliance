# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.report.purchase_register.purchase_register import _execute

gst_settings = frappe.get_cached_doc("GST Settings")


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

    if gst_settings.enable_reverse_charge_in_sales:
        additional_table_columns.append(
            dict(
                fieldtype="Check",
                label="Is Reverse Charge",
                fieldname="is_reverse_charge",
                width=120,
            ),
        )
        additional_query_columns.append("is_reverse_charge")

    # ToDo: Add column after confirm export field in Purchase Invoice
    # if gst_settings.enable_overseas_transactions:
    #     additional_table_columns.append(
    #         dict(
    #         fieldtype="Check",
    #         label="Is Export With GST",
    #         fieldname="is_export_with_gst",
    #         width=120,
    #     )
    #     )
    #     additional_query_columns.append("is_export_with_gst")

    return _execute(filters, additional_table_columns, additional_query_columns)
