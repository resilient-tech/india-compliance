# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import (
    _execute,
)


def execute(filters=None):
    values = _execute(
        filters,
        additional_table_columns=[
            dict(
                fieldtype="Data",
                label="Customer GSTIN",
                fieldname="customer_gstin",
                width=120,
            ),
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
                label="Reverse Charge",
                fieldname="is_reverse_charge",
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
                label="Export Type",
                fieldname="export_with_payment_of_tax",
                width=120,
            ),
            dict(
                fieldtype="Data",
                label="E-Commerce GSTIN",
                fieldname="ecommerce_gstin",
                width=130,
            ),
            dict(
                fieldtype="Data", label="HSN Code", fieldname="gst_hsn_code", width=120
            ),
        ],
        additional_query_columns=[
            "customer_gstin",
            "billing_address_gstin",
            "company_gstin",
            "place_of_supply",
            "is_reverse_charge",
            "gst_category",
            "export_with_payment_of_tax",
            "ecommerce_gstin",
            "gst_hsn_code",
        ],
    )

    # Result (values[1]) is returned as list of dicts
    for row in values[1]:
        row["is_reverse_charge"] = "Y" if row["is_reverse_charge"] else "N"
        row["export_with_payment_of_tax"] = (
            "With Payment of Tax"
            if row["export_with_payment_of_tax"]
            else "Without Payment of Tax"
        )

    return values
