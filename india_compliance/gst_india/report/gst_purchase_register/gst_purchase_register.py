# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.report.purchase_register.purchase_register import _execute


def execute(filters=None):
    columns, data = _execute(
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
                fieldtype="Check",
                label="Is Reverse Charge",
                fieldname="is_reverse_charge",
                width=120,
            ),
            dict(
                fieldtype="Data",
                label="GST Category",
                fieldname="gst_category",
                width=120,
            ),
        ],
        additional_query_columns=[
            "supplier_gstin",
            "company_gstin",
            "is_reverse_charge",
            "gst_category",
        ],
    )

    update_bill_of_entry_data(filters, data, columns)
    return columns, data


def update_bill_of_entry_data(filters, data, columns):
    for row in data:
        if not (
            boe := frappe.db.exists(
                "Bill of Entry", {"purchase_invoice": row[0], "docstatus": 1}
            )
        ):
            continue

        boe_doc = frappe.get_cached_doc("Bill of Entry", boe)

        total_tax = 0
        for tax in boe_doc.taxes:
            total_tax += tax.tax_amount
            for idx, column in enumerate(columns):
                if not isinstance(column, str):
                    continue
                if column.split(":")[0] == tax.account_head:
                    row[idx] += tax.tax_amount
                if column.split(":")[0] == "Total Tax":
                    row[idx] += total_tax
