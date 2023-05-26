# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from erpnext.accounts.report.purchase_register.purchase_register import _execute

from india_compliance.gst_india.report.bill_of_entry_summary.bill_of_entry_summary import (
    update_purchase_invoice_query,
)
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
    bill_of_entries = get_bill_of_entry(filters)

    if not bill_of_entries:
        return columns, data

    insert_additional_columns(data, columns, bill_of_entries)
    input_accounts = get_gst_accounts_by_type(filters.get("company"), "Input")

    for inv, boe_data in bill_of_entries.items():
        row = []
        for _column in columns:
            column_label = (
                _column.split(":")[0].strip()
                if isinstance(_column, str)
                else _column.get("label")
            )

            if column_label == "Invoice":
                row.append(inv)

            elif column_label in input_accounts.values():
                for account in boe_data.account_detail:

                    if column_label == account.account_head:
                        if account.account_head == input_accounts.igst_account:
                            row.append(account.tax_amount)
                            break

                        elif account.account_head == input_accounts.cess_account:
                            row.append(account.tax_amount)
                            break
                else:
                    row.append(0)

            elif column_label == "Total Tax":
                row.append(boe_data.total_taxes)

            else:
                row.append("")

        data.append(row)


def insert_additional_columns(data, columns, bill_of_entries, is_itemised_report=False):
    tax_accounts = list(
        set(
            account.account_head
            for key, value in bill_of_entries.items()
            for account in value.account_detail
        )
    )

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

            for row in data:
                if account in boe_tax_accounts:
                    row[frappe.scrub(account + " Rate")] = 0
                    row[frappe.scrub(account + " Amount")] = 0
        else:
            total_tax_column_index = columns.index("Total Tax:Currency/currency:120")

            if not is_column_exists(columns, (account + ":Currency/currency:120")):
                boe_tax_accounts.append(account)
                columns.insert(
                    total_tax_column_index,
                    _(account + ":Currency/currency:120"),
                )

            for row in data:
                if account in boe_tax_accounts:
                    row.insert(total_tax_column_index, 0)

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


def get_bill_of_entry(filters) -> dict:
    bill_of_entry = frappe.qb.DocType("Bill of Entry")
    bill_of_entry_taxes = frappe.qb.DocType("Bill of Entry Taxes")

    query = (
        frappe.qb.from_(bill_of_entry)
        .inner_join(bill_of_entry_taxes)
        .on(bill_of_entry.name == bill_of_entry_taxes.parent)
        .select(
            bill_of_entry.name,
            bill_of_entry.posting_date,
            bill_of_entry.purchase_invoice,
            bill_of_entry.total_customs_duty,
            bill_of_entry.total_taxes,
            bill_of_entry.total_amount_payable,
            bill_of_entry_taxes.account_head,
            bill_of_entry_taxes.rate,
            bill_of_entry_taxes.tax_amount,
        )
        .where(bill_of_entry.docstatus == 1)
        .where(
            bill_of_entry.bill_of_entry_date[
                filters.get("from_date") : filters.get("to_date")
            ]
        )
        .where(
            bill_of_entry_taxes.account_head.isnotnull()
            and bill_of_entry_taxes.account_head != ""
        )
        .where(bill_of_entry.company == filters.get("company"))
    )

    query = update_purchase_invoice_query(query)

    boe_data = query.run(as_dict=1)

    boe_details = frappe._dict()

    for data in boe_data:
        detail = frappe._dict(
            account_head=data.account_head, rate=data.rate, tax_amount=data.tax_amount
        )
        inv_data = boe_details.setdefault(
            data.purchase_invoice,
            frappe._dict(
                invoice=data.purchase_invoice,
                bill_of_entry=data.name,
                total_customs_duty=data.total_customs_duty,
                total_taxes=data.total_taxes,
                total_amount_payable=data.total_amount_payable,
                account_detail=[],
            ),
        )

        if detail not in inv_data.account_detail:
            inv_data.account_detail.append(detail)

    return boe_details
