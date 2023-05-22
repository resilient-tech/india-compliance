# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
from itertools import chain

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
    doctype = "Bill of Entry"
    boe_tax_accounts = insert_additional_columns(data, columns)
    input_accounts = get_gst_accounts_by_type(filters.get("company"), "Input")

    for idx, _column in enumerate(columns):
        column_label = (
            _column.split(":")[0].strip()
            if isinstance(_column, str)
            else _column.get("label")
        )

        for row in data:
            if column_label in boe_tax_accounts:
                row.insert(idx, 0)

            purchase_invoice_no = (
                row[0] if isinstance(row, list) else row.get("invoice")
            )

            if boe_doc := get_bill_of_entry(doctype, purchase_invoice_no):
                for tax in boe_doc.taxes:
                    if (
                        column_label == tax.account_head
                        and tax.account_head == input_accounts.igst_account
                    ):
                        row[idx] += tax.tax_amount

                    elif (
                        column_label == tax.account_head
                        and tax.account_head == input_accounts.cess_account
                    ):
                        row[idx] += tax.tax_amount

                    elif column_label == "Total Tax":
                        row[idx] += tax.tax_amount

                if column_label in ("Grand Total", "Rounded Total"):
                    row[idx] += boe_doc.total_taxes


def get_additional_tax_accounts(data):
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")

    invoices = tuple(
        row[0] if isinstance(row, list) else row.get("invoice") for row in data
    )
    return (
        frappe.qb.from_(bill_of_entry)
        .inner_join(boe_taxes)
        .on(bill_of_entry.name == boe_taxes.parent)
        .select(boe_taxes.account_head)
        .where(bill_of_entry.docstatus == 1)
        .where(boe_taxes.account_head.isnotnull() and boe_taxes.account_head != "")
        .where(bill_of_entry.purchase_invoice.isin(invoices))
        .orderby(boe_taxes.account_head)
        .distinct()
        .run(as_list=True)
    )


def insert_additional_columns(data, columns, is_itemised_report=False):
    tax_accounts = list(chain(*get_additional_tax_accounts(data)))

    boe_tax_accounts = []
    for account in tax_accounts:
        if is_itemised_report:
            # In GST Purchase Register Column name as account name only But in Itemised Purchase Register column name is description of account head, so the hack to match column name for IGST
            account = "Input Tax IGST @ 18.0" if "IGST" in account else account
            total_tax_column_index = next(
                (
                    index
                    for (index, row) in enumerate(columns)
                    if row.get("label") == "Total Tax"
                ),
                None,
            )

            if not is_column_exists(columns, account):
                boe_tax_accounts.append(account)

                columns.insert(
                    total_tax_column_index,
                    {
                        "label": _(account + " Rate"),
                        "fieldname": frappe.scrub(account + " Rate"),
                        "fieldtype": "Float",
                        "width": 100,
                    },
                )

                columns.insert(
                    total_tax_column_index + 1,
                    {
                        "label": _(account + " Amount"),
                        "fieldname": frappe.scrub(account + " Amount"),
                        "fieldtype": "Currency",
                        "options": "currency",
                        "width": 100,
                    },
                )
        else:
            total_tax_column_index = columns.index("Total Tax:Currency/currency:120")

            if not is_column_exists(columns, (account + ":Currency/currency:120")):
                boe_tax_accounts.append(account)
                columns.insert(
                    total_tax_column_index,
                    _(account + ":Currency/currency:120"),
                )

    return boe_tax_accounts


def is_column_exists(columns, key):
    for column in columns:
        if isinstance(column, dict):
            if key in column.get("label") or column.get("label") == key:
                return True
        if isinstance(column, str):
            if key in columns:
                return True
    return False


def get_bill_of_entry(doctype, invoice):
    boe = frappe.db.exists(doctype, {"purchase_invoice": invoice, "docstatus": 1})
    if not boe:
        return

    doc = frappe.get_cached_doc(doctype, boe)
    return doc
