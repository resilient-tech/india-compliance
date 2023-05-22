# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


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
    doctype = "Bill of Entry"
    boe_tax_accounts = insert_additional_columns(data, columns, with_rate=True)
    input_accounts = get_gst_accounts_by_type(filters.get("company"), "Input")

    for idx, _column in enumerate(columns):
        column_label = _column.get("label")

        if "@" in column_label:
            column_label = column_label.split("@")[0].strip()
        elif column_label.endswith("Rate") and len(column_label) > 4:
            column_label = column_label[:-5]
        elif column_label.endswith("Amount") and len(column_label) > 4:
            column_label = column_label[:-7]

        fieldname = _column.get("fieldname")

        for row in data:
            if column_label in boe_tax_accounts:
                if not row.get(fieldname):
                    row[fieldname] = 0

            purchase_invoice_no = (
                row[0] if isinstance(row, list) else row.get("invoice")
            )

            boe_doc = get_bill_of_entry(doctype, purchase_invoice_no)

            if boe_doc:
                for tax in boe_doc.taxes:
                    if (
                        column_label in tax.account_head
                        and tax.account_head == input_accounts.igst_account
                    ):
                        if _column.get("fieldname").endswith("amount"):
                            row[fieldname] += tax.tax_amount
                        elif _column.get("fieldname").endswith("rate"):
                            row[fieldname] = tax.rate

                    elif (
                        column_label in tax.account_head
                        and tax.account_head == input_accounts.cess_account
                    ):
                        if _column.get("fieldname").endswith("amount"):
                            row[fieldname] += tax.tax_amount
                        elif _column.get("fieldname").endswith("rate"):
                            row[fieldname] = tax.rate

                    elif column_label == "Total Tax":
                        row[fieldname] += tax.tax_amount

                if column_label == "Total":
                    row[fieldname] += boe_doc.total_taxes
