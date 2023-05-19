# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from erpnext.accounts.report.purchase_register.purchase_register import _execute

from india_compliance.gst_india.utils import get_gst_accounts_by_type


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
    boe_tax_accounts = insert_additional_columns(data, columns)
    doctype = "Bill of Entry"
    input_accounts = get_gst_accounts_by_type(filters.get("company"), "Input")

    for row in data:
        boe = frappe.db.exists(doctype, {"purchase_invoice": row[0], "docstatus": 1})
        boe_doc = frappe.get_doc(doctype, boe) if boe else None

        for idx, _column in enumerate(columns):
            if not isinstance(_column, str):
                continue

            column = _column.split(":")[0]

            if column in boe_tax_accounts:
                row.insert(idx, 0)

            if boe_doc:
                for tax in boe_doc.taxes:
                    if (
                        column == tax.account_head
                        and tax.account_head == input_accounts.igst_account
                    ):
                        row[idx] += tax.tax_amount

                    elif (
                        column == tax.account_head
                        and tax.account_head == input_accounts.cess_account
                    ):
                        row[idx] += tax.tax_amount

                    elif column == "Total Tax":
                        row[idx] += tax.tax_amount

                if column == "Total Customs Duty":
                    row[idx] += boe_doc.total_customs_duty

                if column == "Grand Total":
                    row[idx] += boe_doc.total_amount_payable

                if column == "Rounded Total":
                    row[idx] += round(boe_doc.total_amount_payable)


def get_additional_tax_accounts(data):
    return frappe.db.sql_list(
        """
            select
                distinct boe_taxes.account_head
            from
                `tabBill of Entry` as boe
            INNER JOIN
                `tabBill of Entry Taxes` as boe_taxes
            ON
                boe.name = boe_taxes.parent
            where
                boe.docstatus = 1
                and (boe_taxes.account_head is not null and boe_taxes.account_head != '')
                and boe.purchase_invoice in (%s) order by boe_taxes.account_head"""
        % ", ".join(["%s"] * len(data)),
        tuple(inv[0] for inv in data),
    )


def insert_additional_columns(data, columns):
    tax_accounts = get_additional_tax_accounts(data)
    total_tax_column_index = columns.index("Total Tax:Currency/currency:120")

    boe_tax_accounts = []
    for account in tax_accounts + ["Total Customs Duty"]:
        if (account + ":Currency/currency:120") not in columns:
            boe_tax_accounts.append(account)
            columns.insert(
                total_tax_column_index, _(account + ":Currency/currency:120")
            )

    return boe_tax_accounts
