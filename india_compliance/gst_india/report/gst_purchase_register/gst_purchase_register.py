# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from erpnext.accounts.report.purchase_register.purchase_register import _execute


def execute(filters=None):
    columns, result = _execute(
        filters,
        additional_table_columns=[
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
                label="Reverse Charge",
                fieldname="reverse_charge",
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
        ],
        additional_query_columns=[
            "supplier_gstin",
            "company_gstin",
            "reverse_charge",
            "gst_category",
            "export_with_payment_of_tax",
            "ecommerce_gstin",
        ],
    )

    index = next(
        i
        for i, item in enumerate(columns)
        if isinstance(item, dict) and item["fieldname"] == "export_with_payment_of_tax"
    )

    for row in result:
        row[index] = "With Payment of Tax" if row[index] else "Without Payment of Tax"

    return columns, result
