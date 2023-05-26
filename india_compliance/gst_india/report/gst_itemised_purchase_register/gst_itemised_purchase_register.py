# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.report.item_wise_purchase_register.item_wise_purchase_register import (
    _execute,
)

from india_compliance.gst_india.report.gst_purchase_register.gst_purchase_register import (
    get_bill_of_entry,
    insert_additional_columns,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type


def execute(filters=None):
    columns, data, value1, value2, value3, skip_total_row = _execute(
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
            dict(
                fieldtype="Data", label="HSN Code", fieldname="gst_hsn_code", width=120
            ),
            dict(
                fieldtype="Data",
                label="Supplier Invoice No",
                fieldname="bill_no",
                width=120,
            ),
            dict(
                fieldtype="Date",
                label="Supplier Invoice Date",
                fieldname="bill_date",
                width=100,
            ),
        ],
        additional_query_columns=[
            "supplier_gstin",
            "company_gstin",
            "is_reverse_charge",
            "gst_category",
            "gst_hsn_code",
            "bill_no",
            "bill_date",
        ],
    )

    update_bill_of_entry_data(filters, data, columns)
    return columns, data, value1, value2, value3, skip_total_row


def update_bill_of_entry_data(filters, data, columns):
    # Used separate function because data is list of dictioanries here.

    bill_of_entries = get_bill_of_entry(filters)

    if not bill_of_entries:
        return columns, data

    insert_additional_columns(data, columns, bill_of_entries, is_itemised_report=True)
    input_accounts = get_gst_accounts_by_type(filters.get("company"), "Input")

    for inv, boe_data in bill_of_entries.items():
        row = frappe._dict()
        for _column in columns:
            column_label = _column.get("label")
            fieldname = _column.get("fieldname")

            # To extract account names from columns because column names are like Input Tax CGST @ 9.0 Amount and TDS - RT Amount
            if "@" in column_label:
                column_label = column_label.split("@")[0].strip()
            elif column_label.endswith("Rate") and len(column_label) > 4:
                column_label = column_label[:-5]
            elif column_label.endswith("Amount") and len(column_label) > 7:
                column_label = column_label[:-7]

            if column_label == "Invoice":
                row[fieldname] = inv

            elif [
                value
                for key, value in input_accounts.items()
                if value is not None and column_label in value
            ]:
                for account in boe_data.account_detail:
                    if column_label in account.account_head:
                        if account.account_head == input_accounts.igst_account:
                            if fieldname.endswith("amount"):
                                row[fieldname] = account.tax_amount
                            elif fieldname.endswith("rate"):
                                row[fieldname] = account.rate
                            break

                        elif account.account_head == input_accounts.cess_account:
                            if fieldname.endswith("amount"):
                                row[fieldname] = account.tax_amount
                            elif fieldname.endswith("rate"):
                                row[fieldname] = account.rate
                            break
                else:
                    row[fieldname] = 0

            elif column_label == "Total Tax":
                row[fieldname] = boe_data.total_taxes

            else:
                row[fieldname] = ""

        data.append(row)
