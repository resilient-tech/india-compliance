"""
Export GSTR-1 data to excel or json
"""

import json
from datetime import datetime

import frappe
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta import get_period
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import (
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    ExcelWidth,
    GSTR1_DataFields,
    GSTR1_Excel_Categories,
    GSTR1_Gov_Categories,
    GSTR1_ItemFields,
    GSTR1_SubCategories,
    get_file_name,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_gov_data_format,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    get_category_wise_data as _get_category_wise_data,
)


class GovExcel:
    """
    Export GSTR-1 data to excel
    """

    AMOUNT_DATA_FORMAT = {
        "number_format": "#,##0.00",
    }

    PERCENTAGE_DATA_FORMAT = {
        "number_format": "0.00",
    }

    DATE_FORMAT = {
        "number_format": "dd-mmm-yy",
    }

    def generate(self, gstin, period):
        """
        Build excel file
        """
        self.gstin = gstin
        self.period = period
        gstr_1_log = frappe.get_doc("GSTR-1 Filed Log", f"{period}-{gstin}")

        self.file_field = "filed" if gstr_1_log.filed else "books"
        data = gstr_1_log.load_data(self.file_field)[self.file_field]
        data = self.process_data(data)
        self.build_excel(data)

    def build_excel(self, data):
        excel = ExcelExporter()
        for category, cat_data in data.items():
            excel.create_sheet(
                sheet_name=JSON_CATEGORY_EXCEL_CATEGORY_MAPPING.get(category, category),
                headers=self.get_category_headers(category),
                data=cat_data,
                add_totals=False,
                default_data_format={"height": 15},
            )

        excel.remove_sheet("Sheet")
        excel.export(get_file_name("gov", self.gstin, self.period))

    def get_category_headers(self, category):
        return getattr(self, f"get_{category.lower()}_headers")()

    def get_b2b_headers(self):
        return [
            {
                "label": "GSTIN/UIN of Recipient",
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "header_format": {
                    "width": ExcelWidth.GSTIN.value,
                },
            },
            {
                "label": "Receiver Name",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "header_format": {
                    "width": ExcelWidth.NAME.value,
                },
            },
            {
                "label": "Invoice Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": "Invoice date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                },
            },
            {
                "label": "Invoice Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Reverse Charge",
                "fieldname": GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {"horizontal": "center"},
                "header_format": {
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Invoice Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "E-Commerce GSTIN",
                # Ignore value, just keep the column
                "fieldname": f"_{GSTR1_DataFields.ECOMMERCE_GSTIN.value}",
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_ItemFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_ItemFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_b2cl_headers(self):
        return [
            {
                "label": "Invoice Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": "Invoice date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                },
            },
            {
                "label": "Invoice Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_ItemFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_ItemFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "E-Commerce GSTIN",
                # Ignore value, just keep the column
                "fieldname": f"_{GSTR1_DataFields.ECOMMERCE_GSTIN.value}",
            },
        ]

    def get_b2cs_headers(self):
        return [
            {
                "label": "Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_DataFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "E-Commerce GSTIN",
                # Ignore value, just keep the column
                "fieldname": f"_{GSTR1_DataFields.ECOMMERCE_GSTIN.value}",
            },
        ]

    def get_cdnr_headers(self):
        return [
            {
                "label": "GSTIN/UIN of Recipient",
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "header_format": {
                    "width": ExcelWidth.GSTIN.value,
                },
            },
            {
                "label": "Receiver Name",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "header_format": {
                    "width": ExcelWidth.NAME.value,
                },
            },
            {
                "label": "Note Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": "Note date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                },
            },
            {
                "label": "Note Type",
                "fieldname": GSTR1_DataFields.TRANSACTION_TYPE.value,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Reverse Charge",
                "fieldname": GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {"horizontal": "center"},
                "header_format": {
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "label": "Note Supply Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Note Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_ItemFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_ItemFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_cdnur_headers(self):
        return [
            {
                "label": "UR Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Note Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": "Note date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                },
            },
            {
                "label": "Note Type",
                "fieldname": GSTR1_DataFields.TRANSACTION_TYPE.value,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Note Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_ItemFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_ItemFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_exp_headers(self):
        return [
            {
                "label": "Export Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Invoice Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": "Invoice date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                },
            },
            {
                "label": "Invoice Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Port Code",
                "fieldname": GSTR1_DataFields.SHIPPING_PORT_CODE.value,
            },
            {
                "label": "Shipping Bill Number",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": "Shipping Bill Date",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_DATE.value,
                "data_format": self.DATE_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_ItemFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_ItemFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_at_headers(self):
        return [
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Gross Advance Received",
                "fieldname": GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_DataFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_txpd_headers(self):
        return [
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.DIFF_PERCENTAGE.value,
                },
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Gross Advance Adjusted",
                "fieldname": GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_DataFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_nil_headers(self):
        return [
            {
                "label": "Description",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Nil Rated Supplies",
                "fieldname": GSTR1_DataFields.NIL_RATED_AMOUNT.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Exempted(other than nil rated/non GST supply)",
                "fieldname": GSTR1_DataFields.EXEMPTED_AMOUNT.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Non-GST Supplies",
                "fieldname": GSTR1_DataFields.NON_GST_AMOUNT.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": "HSN",
                "fieldname": GSTR1_DataFields.HSN_CODE.value,
            },
            {
                "label": "Description",
                "fieldname": GSTR1_DataFields.DESCRIPTION.value,
            },
            {
                "label": "UQC",
                "fieldname": GSTR1_DataFields.UOM.value,
            },
            {
                "label": "Total Quantity",
                "fieldname": GSTR1_DataFields.QUANTITY.value,
                "header_format": {
                    "width": ExcelWidth.QUANTITY.value,
                },
            },
            {
                "label": "Total Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
                "header_format": {
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Integrated Tax Amount",
                "fieldname": GSTR1_DataFields.IGST.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Central Tax Amount",
                "fieldname": GSTR1_DataFields.CGST.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "State/UT Tax Amount",
                "fieldname": GSTR1_DataFields.SGST.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Cess Amount",
                "fieldname": GSTR1_DataFields.CESS.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": "Nature of Document",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Sr. No. From",
                "fieldname": GSTR1_DataFields.FROM_SR.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": "Sr. No. To",
                "fieldname": GSTR1_DataFields.TO_SR.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": "Total Number",
                "fieldname": GSTR1_DataFields.TOTAL_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
            {
                "label": "Cancelled",
                "fieldname": GSTR1_DataFields.CANCELLED_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
        ]

    # UTILITY FUNCTIONS

    CATEGORIES_WITH_ITEMS = {
        GSTR1_Gov_Categories.B2B.value,
        GSTR1_Gov_Categories.B2CL.value,
        GSTR1_Gov_Categories.EXP.value,
        GSTR1_Gov_Categories.CDNR.value,
        GSTR1_Gov_Categories.CDNUR.value,
    }

    def get_category_wise_data(self, input_data):
        return {
            category: self.flatten_to_invoice_list(data)
            for category, data in _get_category_wise_data(input_data).items()
        }

    def create_row(self, invoice_data, item):
        return {
            **invoice_data,
            GSTR1_ItemFields.TAX_RATE.value: item.get(
                GSTR1_ItemFields.TAX_RATE.value, 0
            ),
            GSTR1_ItemFields.TAXABLE_VALUE.value: item.get(
                GSTR1_ItemFields.TAXABLE_VALUE.value, 0
            ),
            GSTR1_ItemFields.CESS.value: item.get(GSTR1_ItemFields.CESS.value, 0),
        }

    def flatten_to_invoice_list(self, input_data):
        return [document for documents in input_data.values() for document in documents]

    def flatten_invoice_items_to_rows(self, input_data):
        return [
            self.create_row(invoice, item)
            for invoice in input_data
            for item in invoice[GSTR1_DataFields.ITEMS.value]
        ]

    FIELD_TRANSFORMATIONS = {
        GSTR1_DataFields.DIFF_PERCENTAGE.value: lambda value: (
            value * 100 if value != 0 else None
        ),
        GSTR1_DataFields.DOC_DATE.value: lambda value: datetime.strptime(
            value, "%Y-%m-%d"
        ),
        GSTR1_DataFields.SHIPPING_BILL_DATE.value: lambda value: datetime.strptime(
            value, "%Y-%m-%d"
        ),
    }

    def modify_row(self, row):
        for field, modifier in self.FIELD_TRANSFORMATIONS.items():
            if field in row:
                row[field] = modifier(row[field])

        return row

    def process_data(self, input_data):
        category_wise_data = self.get_category_wise_data(input_data)

        processed_data = {
            category: [
                self.modify_row(row)
                for row in (
                    self.flatten_invoice_items_to_rows(data)
                    if category in self.CATEGORIES_WITH_ITEMS
                    else data
                )
            ]
            for category, data in category_wise_data.items()
        }

        # calculate document_value for HSN
        for row in processed_data.get(GSTR1_Gov_Categories.HSN.value, []):
            row[GSTR1_DataFields.DOC_VALUE.value] = sum(
                (
                    row.get(GSTR1_DataFields.TAXABLE_VALUE.value, 0),
                    row.get(GSTR1_DataFields.IGST.value, 0),
                    row.get(GSTR1_DataFields.CGST.value, 0),
                    row.get(GSTR1_DataFields.SGST.value, 0),
                    row.get(GSTR1_DataFields.CESS.value, 0),
                )
            )

        return processed_data


AMOUNT_FORMAT = "#,##0.00"
DATE_FORMAT = "dd-mmm-yy"


class BooksExcel:

    AMOUNT_HEADERS = [
        {
            "fieldname": GSTR1_DataFields.IGST.value,
            "label": "IGST",
            "data_format": {"number_format": AMOUNT_FORMAT},
        },
        {
            "fieldname": GSTR1_DataFields.CGST.value,
            "label": "CGST",
            "data_format": {"number_format": AMOUNT_FORMAT},
        },
        {
            "fieldname": GSTR1_DataFields.SGST.value,
            "label": "SGST",
            "data_format": {"number_format": AMOUNT_FORMAT},
        },
        {
            "fieldname": GSTR1_DataFields.CESS.value,
            "label": "CESS",
            "data_format": {"number_format": AMOUNT_FORMAT},
        },
    ]

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        doc = frappe.get_doc("GSTR-1 Filed Log", f"{self.period}-{company_gstin}")
        self.data = doc.load_data("books")["books"]

    def export_data(self):
        excel = ExcelExporter()
        excel.remove_sheet("Sheet")

        default_data_format = {"height": 15}

        excel.create_sheet(
            sheet_name="invoices",
            headers=self.get_document_headers(),
            data=self.get_document_data(),
            default_data_format=default_data_format,
            add_totals=False,
        )
        if hsn_data := self.data.get(GSTR1_SubCategories.HSN.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.HSN.value,
                headers=self.get_hsn_summary_headers(),
                data=hsn_data,
                default_data_format=default_data_format,
                add_totals=False,
            )

        if at_received_data := self.data.get(GSTR1_SubCategories.AT.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.AT.value,
                headers=self.get_at_received_headers(),
                data=at_received_data,
                default_data_format=default_data_format,
                add_totals=False,
            )

        if at_adjusted_data := self.data.get(GSTR1_SubCategories.TXP.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.TXP.value,
                headers=self.get_at_adjusted_headers(),
                data=at_adjusted_data,
                default_data_format=default_data_format,
                add_totals=False,
            )

        if doc_issued_data := self.data.get(GSTR1_SubCategories.DOC_ISSUE.value):
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.DOC_ISSUE.value,
                headers=self.get_doc_issue_headers(),
                data=doc_issued_data,
                default_data_format=default_data_format,
                add_totals=False,
            )

        excel.export(get_file_name("books", self.company_gstin, self.period))

    def get_document_data(self):
        category = [
            GSTR1_SubCategories.B2B_REGULAR.value,
            GSTR1_SubCategories.B2B_REVERSE_CHARGE.value,
            GSTR1_SubCategories.SEZWP.value,
            GSTR1_SubCategories.SEZWOP.value,
            GSTR1_SubCategories.DE.value,
            GSTR1_SubCategories.EXPWP.value,
            GSTR1_SubCategories.EXPWOP.value,
            GSTR1_SubCategories.B2CL.value,
            GSTR1_SubCategories.B2CS.value,
            GSTR1_SubCategories.NIL_EXEMPT.value,
            GSTR1_SubCategories.CDNR.value,
            GSTR1_SubCategories.CDNUR.value,
        ]

        category_data = []
        for key, values in self.data.items():
            if key not in category:
                continue

            if key in (
                GSTR1_SubCategories.B2CS.value,
                GSTR1_SubCategories.NIL_EXEMPT.value,
            ):
                category_data.extend(values)
                continue

            for row in values:
                dict = row
                for item in row["items"]:
                    category_data.extend([{**dict, **item}])

        return category_data

    def get_document_headers(self):
        return [
            {
                "label": "Transaction Type",
                "fieldname": GSTR1_DataFields.TRANSACTION_TYPE.value,
            },
            {
                "label": "Document Date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": "Document Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": "Customer GSTIN",
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "label": "Customer Name",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": "Document Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Shipping Bill Number",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": "Shipping Bill Date",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_DATE.value,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": "Port Code",
                "fieldname": GSTR1_DataFields.SHIPPING_PORT_CODE.value,
            },
            {
                "label": "Reverse Charge",
                "fieldname": GSTR1_DataFields.REVERSE_CHARGE.value,
                "header_format": {"width": ExcelWidth.REVERSE_CHARGE.value},
            },
            {
                "label": "Upload Status",
                "fieldname": GSTR1_DataFields.UPLOAD_STATUS.value,
            },
            {
                "label": "Place of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            *self.AMOUNT_HEADERS,
            {
                "label": "Document Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
            },
        ]

    def get_at_received_headers(self):
        return [
            {
                "label": "Advance Date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": "Payment Entry Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": "Customer",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": "Place of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            *self.AMOUNT_HEADERS,
            {
                "label": "Amount Received",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
            },
        ]

    def get_at_adjusted_headers(self):
        return [
            {
                "label": "Adjustment Date",
                "fieldname": GSTR1_DataFields.DOC_DATE,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": "Adjustment Entry Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": "Customer ",
                "fieldname": GSTR1_DataFields.CUST_NAME,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": "Place of Supply",
                "fieldname": GSTR1_DataFields.POS,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            *self.AMOUNT_HEADERS,
            {
                "label": "Amount Adjusted",
                "fieldname": GSTR1_DataFields.DOC_VALUE,
            },
        ]

    def get_hsn_summary_headers(self):
        return [
            {
                "label": "HSN Code",
                "fieldname": GSTR1_DataFields.HSN_CODE.value,
            },
            {
                "label": "Description",
                "fieldname": GSTR1_DataFields.DESCRIPTION.value,
                "header_format": {"width": ExcelWidth.DESCRIPTION.value},
            },
            {
                "label": "UOM",
                "fieldname": GSTR1_DataFields.UOM.value,
            },
            {
                "label": "Total Quantity",
                "fieldname": GSTR1_DataFields.QUANTITY.value,
                "header_format": {"width": ExcelWidth.QUANTITY.value},
            },
            *self.AMOUNT_HEADERS,
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": "Document Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Sr No From",
                "fieldname": GSTR1_DataFields.FROM_SR.value,
            },
            {
                "label": "Sr No To",
                "fieldname": GSTR1_DataFields.TO_SR.value,
            },
            {
                "label": "Total Count",
                "fieldname": GSTR1_DataFields.TOTAL_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
            {
                "label": "Draft Count",
                "fieldname": GSTR1_DataFields.DRAFT_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
            {
                "label": "Cancelled Count",
                "fieldname": GSTR1_DataFields.CANCELLED_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
        ]


class ReconcileExcel:
    COLOR_PALLATE = frappe._dict(
        {
            "dark_gray": "d9d9d9",
            "light_gray": "f2f2f2",
            "dark_pink": "e6b9b8",
            "light_pink": "f2dcdb",
            "sky_blue": "c6d9f1",
            "light_blue": "dce6f2",
            "green": "d7e4bd",
            "light_green": "ebf1de",
        }
    )

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        doc = frappe.get_doc("GSTR-1 Filed Log", f"{self.period}-{company_gstin}")

        self.summary = doc.load_data("reconcile_summary")["reconcile_summary"]
        self.data = doc.load_data("reconcile")["reconcile"]

    def export_data(self):
        excel = ExcelExporter()
        excel.remove_sheet("Sheet")

        default_header_format = {"bg_color": self.COLOR_PALLATE.dark_gray}
        default_data_format = {"bg_color": self.COLOR_PALLATE.light_gray}

        excel.create_sheet(
            sheet_name="reconcile summary",
            headers=self.get_reconcile_summary_headers(),
            data=self.get_reconcile_summary_data(),
            default_data_format=default_data_format,
            default_header_format=default_header_format,
            add_totals=False,
        )

        if b2b_data := self.get_b2b_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.B2B.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_b2b_headers(),
                data=b2b_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if b2cl_data := self.get_b2cl_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.B2CL.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_b2cl_headers(),
                data=b2cl_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if exports_data := self.get_exports_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.EXP.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_exports_headers(),
                data=exports_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if b2cs_data := self.get_b2cs_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.B2CS.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_b2cs_headers(),
                data=b2cs_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if nil_exempt_data := self.get_nil_exempt_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.NIL_EXEMPT.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_nil_exempt_headers(),
                data=nil_exempt_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if cdnr_data := self.get_cdnr_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.CDNR.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_cdnr_headers(),
                data=cdnr_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if cdnur_data := self.get_cdnur_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.CDNUR.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_cdnur_headers(),
                data=cdnur_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if doc_issue_data := self.get_doc_issue_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.DOC_ISSUE.value,
                merged_headers=self.get_merge_headers_for_doc_issue(),
                headers=self.get_doc_issue_headers(),
                data=doc_issue_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if hsn_data := self.get_hsn_summary_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.HSN.value,
                merged_headers=self.get_merge_headers_for_hsn_summary(),
                headers=self.get_hsn_summary_headers(),
                data=hsn_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if at_data := self.get_at_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.AT.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_at_txp_headers(),
                data=at_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        if txp_data := self.get_txp_data():
            excel.create_sheet(
                sheet_name=GSTR1_Excel_Categories.TXP.value,
                merged_headers=self.get_merge_headers(),
                headers=self.get_at_txp_headers(),
                data=txp_data,
                default_data_format=default_data_format,
                default_header_format=default_header_format,
                add_totals=False,
            )

        excel.export(get_file_name("reconcile", self.company_gstin, self.period))

    def get_merge_headers(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataFields.POS.value,
                    "books_" + GSTR1_DataFields.CESS.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataFields.POS.value,
                    "gstr_1_" + GSTR1_DataFields.CESS.value,
                ],
            }
        )

    def get_merge_headers_for_doc_issue(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataFields.FROM_SR.value,
                    "books_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataFields.FROM_SR.value,
                    "gstr_1_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                ],
            }
        )

    def get_merge_headers_for_hsn_summary(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataFields.UOM.value,
                    "books_" + GSTR1_DataFields.CESS.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataFields.UOM.value,
                    "gstr_1_" + GSTR1_DataFields.CESS.value,
                ],
            }
        )

    def get_reconcile_summary_headers(self):
        headers = [
            {
                "fieldname": "description",
                "label": "Description",
                "header_format": {"width": ExcelWidth.DESCRIPTION.value},
            },
            {
                "fieldname": "total_taxable_value",
                "label": "Taxable Value",
                "data_format": {"number_format": AMOUNT_FORMAT},
            },
            {
                "fieldname": "total_igst_amount",
                "label": "IGST",
                "data_format": {"number_format": AMOUNT_FORMAT},
            },
            {
                "fieldname": "total_cgst_amount",
                "label": "CGST",
                "data_format": {"number_format": AMOUNT_FORMAT},
            },
            {
                "fieldname": "total_sgst_amount",
                "label": "SGST",
                "data_format": {"number_format": AMOUNT_FORMAT},
            },
            {
                "fieldname": "total_cess_amount",
                "label": "CESS",
                "data_format": {"number_format": AMOUNT_FORMAT},
            },
        ]
        return headers

    def get_reconcile_summary_data(self):
        excel_data = []
        for row in self.summary:
            if row["indent"] == 1:
                continue
            excel_data.append(row)

        return excel_data

    def get_b2b_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_b2b_data(self):
        b2b_regular = self.data.get(GSTR1_SubCategories.B2B_REGULAR.value, [])
        b2b_reverse_charge = self.data.get(
            GSTR1_SubCategories.B2B_REVERSE_CHARGE.value, []
        )
        sezwop = self.data.get(GSTR1_SubCategories.SEZWOP.value, [])
        sezwp = self.data.get(GSTR1_SubCategories.SEZWP.value, [])
        deemed_export = self.data.get(GSTR1_SubCategories.DE.value, [])

        b2b_data = b2b_regular + b2b_reverse_charge + sezwop + sezwp + deemed_export

        excel_data = []

        for row in b2b_data:
            row_dict = self.get_row_dict(row)

            excel_data.append(row_dict)

        return excel_data

    def get_b2cl_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_b2cl_data(self):
        b2cl_data = self.data.get(GSTR1_SubCategories.B2CL.value, [])

        excel_data = []

        for row in b2cl_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_exports_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_NUMBER.value,
                "label": "Shipping Bill Number",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_DATE.value,
                "label": "Shipping Bill Date",
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "fieldname": GSTR1_DataFields.SHIPPING_PORT_CODE.value,
                "label": "Shipping Port Code",
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_exports_data(self):
        expwp = self.data.get(GSTR1_SubCategories.EXPWP.value, [])
        expwop = self.data.get(GSTR1_SubCategories.EXPWOP.value, [])

        exports_data = expwp + expwop

        excel_data = []

        for row in exports_data:
            row_dict = self.get_row_dict(row)
            row_dict.update(
                {
                    GSTR1_DataFields.SHIPPING_BILL_NUMBER.value: row.get(
                        "shipping_bill_number"
                    ),
                    GSTR1_DataFields.SHIPPING_BILL_DATE.value: row.get(
                        "shipping_bill_date"
                    ),
                    GSTR1_DataFields.SHIPPING_PORT_CODE.value: row.get(
                        "shipping_port_code"
                    ),
                }
            )

            excel_data.append(row_dict)

        return excel_data

    def get_b2cs_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_b2cs_data(self):
        b2cs_data = self.data.get(GSTR1_SubCategories.B2CS.value, [])

        excel_data = []

        for row in b2cs_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_nil_exempt_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_nil_exempt_data(self):
        nil_exempt_data = self.data.get(GSTR1_SubCategories.NIL_EXEMPT.value, [])

        excel_data = []

        for row in nil_exempt_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_cdnr_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_cdnr_data(self):
        cdnr_data = self.data.get(GSTR1_SubCategories.CDNR.value, [])

        excel_data = []

        for row in cdnr_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_cdnur_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
                "label": "Document Type",
            },
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Document Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Document No",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
                "label": "Customer GSTIN",
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "Place of Supply",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "label": "Reverse Charge",
                "compare_with": "books_" + GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_cdnur_data(self):
        cdnr_data = self.data.get(GSTR1_SubCategories.CDNUR.value, [])

        excel_data = []

        for row in cdnr_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_doc_issue_headers(self):
        headers = [
            {"fieldname": GSTR1_DataFields.DOC_TYPE.value, "label": "Document Type"},
            {
                "fieldname": "match_status",
                "label": "Match Status",
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.FROM_SR.value,
                "label": "SR No From",
                "compare_with": "gstr_1_" + GSTR1_DataFields.FROM_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TO_SR.value,
                "label": "SR No To",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TO_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "label": "Total Count",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "label": "Cancelled Count",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.FROM_SR.value,
                "label": "Sr No From",
                "compare_with": "books_" + GSTR1_DataFields.FROM_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TO_SR.value,
                "label": "Sr No To",
                "compare_with": "books_" + GSTR1_DataFields.TO_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "label": "Total Count",
                "compare_with": "books_" + GSTR1_DataFields.TOTAL_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "label": "Cancelled Count",
                "compare_with": "books_" + GSTR1_DataFields.CANCELLED_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
        ]

        return headers

    def get_doc_issue_data(self):
        doc_issue_data = self.data.get(GSTR1_SubCategories.DOC_ISSUE.value, [])

        excel_data = []

        for row in doc_issue_data:
            books = row.get("books", {})
            gstr_1 = row.get("gov", {})
            row_dict = {
                GSTR1_DataFields.DOC_TYPE.value: row.get(
                    GSTR1_DataFields.DOC_TYPE.value
                ),
                "match_status": row.get("match_status"),
                "books_"
                + GSTR1_DataFields.FROM_SR.value: books.get(
                    GSTR1_DataFields.FROM_SR.value
                ),
                "books_"
                + GSTR1_DataFields.TO_SR.value: books.get(GSTR1_DataFields.TO_SR.value),
                "books_"
                + GSTR1_DataFields.TOTAL_COUNT.value: books.get(
                    GSTR1_DataFields.TOTAL_COUNT.value
                ),
                "books_"
                + GSTR1_DataFields.CANCELLED_COUNT.value: (
                    books.get(GSTR1_DataFields.CANCELLED_COUNT.value) or 0
                )
                + (books.get(GSTR1_DataFields.DRAFT_COUNT.value) or 0),
                "gstr_1_"
                + GSTR1_DataFields.FROM_SR.value: gstr_1.get(
                    GSTR1_DataFields.FROM_SR.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TO_SR.value: gstr_1.get(
                    GSTR1_DataFields.TO_SR.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TOTAL_COUNT.value: gstr_1.get(
                    GSTR1_DataFields.TOTAL_COUNT.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.CANCELLED_COUNT.value: (
                    gstr_1.get(GSTR1_DataFields.CANCELLED_COUNT.value) or 0
                )
                + (gstr_1.get(GSTR1_DataFields.DRAFT_COUNT.value) or 0),
            }

            excel_data.append(row_dict)

        return excel_data

    def get_hsn_summary_headers(self):
        headers = [
            {"fieldname": GSTR1_DataFields.HSN_CODE.value, "label": "HSN Code"},
            {"fieldname": GSTR1_DataFields.DESCRIPTION.value, "label": "Description"},
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.UOM.value,
                "label": "UQC",
                "compare_with": "gstr_1_" + GSTR1_DataFields.UOM.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.QUANTITY.value,
                "label": "Quantity",
                "compare_with": "gstr_1_" + GSTR1_DataFields.QUANTITY.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.QUANTITY.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS Amount",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.UOM.value,
                "label": "UQC",
                "compare_with": "books_" + GSTR1_DataFields.UOM.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.QUANTITY.value,
                "label": "Quantity",
                "compare_with": "books_" + GSTR1_DataFields.QUANTITY.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.QUANTITY.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST Amount",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST Amount",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST Amount",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS Amount",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

        return headers

    def get_hsn_summary_data(self):
        hsn_summary_data = self.data.get(GSTR1_SubCategories.HSN.value, [])

        excel_data = []

        for row in hsn_summary_data:
            books = row.get("books", {})
            gstr_1 = row.get("gov", {})

            row_dict = {
                GSTR1_DataFields.HSN_CODE.value: row.get(
                    GSTR1_DataFields.HSN_CODE.value
                ),
                GSTR1_DataFields.DESCRIPTION.value: row.get(
                    GSTR1_DataFields.DESCRIPTION.value
                ),
                "match_status": row.get("match_status"),
                "books_"
                + GSTR1_DataFields.UOM.value: books.get(GSTR1_DataFields.UOM.value),
                "books_"
                + GSTR1_DataFields.QUANTITY.value: books.get(
                    GSTR1_DataFields.QUANTITY.value
                ),
                "books_"
                + GSTR1_DataFields.TAX_RATE.value: books.get(
                    GSTR1_DataFields.TAX_RATE.value
                ),
                "books_"
                + GSTR1_DataFields.TAXABLE_VALUE.value: books.get(
                    GSTR1_DataFields.TAXABLE_VALUE.value
                ),
                "books_"
                + GSTR1_DataFields.IGST.value: books.get(GSTR1_DataFields.IGST.value),
                "books_"
                + GSTR1_DataFields.CGST.value: books.get(GSTR1_DataFields.CGST.value),
                "books_"
                + GSTR1_DataFields.SGST.value: books.get(GSTR1_DataFields.SGST.value),
                "books_"
                + GSTR1_DataFields.CESS.value: books.get(GSTR1_DataFields.CESS.value),
                "gstr_1_"
                + GSTR1_DataFields.UOM.value: gstr_1.get(GSTR1_DataFields.UOM.value),
                "gstr_1_"
                + GSTR1_DataFields.QUANTITY.value: gstr_1.get(
                    GSTR1_DataFields.QUANTITY.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TAX_RATE.value: gstr_1.get(
                    GSTR1_DataFields.TAX_RATE.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.TAXABLE_VALUE.value: gstr_1.get(
                    GSTR1_DataFields.TAXABLE_VALUE.value
                ),
                "gstr_1_"
                + GSTR1_DataFields.IGST.value: gstr_1.get(GSTR1_DataFields.IGST.value),
                "gstr_1_"
                + GSTR1_DataFields.CGST.value: gstr_1.get(GSTR1_DataFields.CGST.value),
                "gstr_1_"
                + GSTR1_DataFields.SGST.value: gstr_1.get(GSTR1_DataFields.SGST.value),
                "gstr_1_"
                + GSTR1_DataFields.CESS.value: gstr_1.get(GSTR1_DataFields.CESS.value),
            }

            self.get_taxable_value_difference(row_dict)
            self.get_tax_difference(row_dict)

            excel_data.append(row_dict)

        return excel_data

    def get_at_txp_headers(self):
        return [
            {
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "label": "Advance Date",
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
                "label": "Payment Entry Number",
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
                "label": "Customer Name",
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": "Match Status"},
            {
                "fieldname": "taxable_value_difference",
                "label": "Taxable Value Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": "Tax Difference",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.POS.value,
                "label": "POS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.POS.value,
                "label": "POS",
                "compare_with": "books_" + GSTR1_DataFields.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAX_RATE.value,
                "label": "Tax Rate",
                "compare_with": "books_" + GSTR1_DataFields.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "label": "Taxable Value",
                "compare_with": "books_" + GSTR1_DataFields.TAXABLE_VALUE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.IGST.value,
                "label": "IGST",
                "compare_with": "books_" + GSTR1_DataFields.IGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CGST.value,
                "label": "CGST",
                "compare_with": "books_" + GSTR1_DataFields.CGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.SGST.value,
                "label": "SGST",
                "compare_with": "books_" + GSTR1_DataFields.SGST.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataFields.CESS.value,
                "label": "CESS",
                "compare_with": "books_" + GSTR1_DataFields.CESS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
        ]

    def get_at_data(self):
        at_data = self.data.get(GSTR1_SubCategories.AT.value, [])

        excel_data = []
        for row in at_data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_txp_data(self):
        txp_adjusted = self.data.get(GSTR1_SubCategories.TXP.value, [])

        excel_data = []
        for row in txp_adjusted:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_row_dict(self, row):
        books = row.get("books", {})
        gstr_1 = row.get("gov", {})
        doc_date = row.get(GSTR1_DataFields.DOC_DATE.value)
        row_dict = {
            GSTR1_DataFields.DOC_DATE.value: getdate(doc_date) if doc_date else "",
            GSTR1_DataFields.DOC_NUMBER.value: row.get(
                GSTR1_DataFields.DOC_NUMBER.value
            ),
            GSTR1_DataFields.CUST_NAME.value: row.get(GSTR1_DataFields.CUST_NAME.value),
            GSTR1_DataFields.CUST_GSTIN.value: row.get(
                GSTR1_DataFields.CUST_GSTIN.value
            ),
            GSTR1_DataFields.DOC_TYPE.value: row.get(GSTR1_DataFields.DOC_TYPE.value),
            "match_status": row.get("match_status"),
            "books_"
            + GSTR1_DataFields.POS.value: books.get(GSTR1_DataFields.POS.value),
            "books_"
            + GSTR1_DataFields.TAX_RATE.value: books.get(
                GSTR1_DataFields.TAX_RATE.value
            ),
            "books_"
            + GSTR1_DataFields.REVERSE_CHARGE.value: books.get(
                GSTR1_DataFields.REVERSE_CHARGE.value
            ),
            "books_"
            + GSTR1_DataFields.TAXABLE_VALUE.value: books.get(
                GSTR1_DataFields.TAXABLE_VALUE.value
            ),
            "books_"
            + GSTR1_DataFields.IGST.value: books.get(GSTR1_DataFields.IGST.value),
            "books_"
            + GSTR1_DataFields.CGST.value: books.get(GSTR1_DataFields.CGST.value),
            "books_"
            + GSTR1_DataFields.SGST.value: books.get(GSTR1_DataFields.SGST.value),
            "books_"
            + GSTR1_DataFields.CESS.value: books.get(GSTR1_DataFields.CESS.value),
            "gstr_1_"
            + GSTR1_DataFields.POS.value: gstr_1.get(GSTR1_DataFields.POS.value),
            "gstr_1_"
            + GSTR1_DataFields.TAX_RATE.value: gstr_1.get(
                GSTR1_DataFields.TAX_RATE.value
            ),
            "gstr_1_"
            + GSTR1_DataFields.REVERSE_CHARGE.value: gstr_1.get(
                GSTR1_DataFields.REVERSE_CHARGE.value
            ),
            "gstr_1_"
            + GSTR1_DataFields.TAXABLE_VALUE.value: gstr_1.get(
                GSTR1_DataFields.TAXABLE_VALUE.value
            ),
            "gstr_1_"
            + GSTR1_DataFields.IGST.value: gstr_1.get(GSTR1_DataFields.IGST.value),
            "gstr_1_"
            + GSTR1_DataFields.CGST.value: gstr_1.get(GSTR1_DataFields.CGST.value),
            "gstr_1_"
            + GSTR1_DataFields.SGST.value: gstr_1.get(GSTR1_DataFields.SGST.value),
            "gstr_1_"
            + GSTR1_DataFields.CESS.value: gstr_1.get(GSTR1_DataFields.CESS.value),
        }

        self.get_taxable_value_difference(row_dict)
        self.get_tax_difference(row_dict)

        return row_dict

    def get_taxable_value_difference(self, row_dict):
        row_dict["taxable_value_difference"] = (
            row_dict["books_" + GSTR1_DataFields.TAXABLE_VALUE.value] or 0
        ) - (row_dict["gstr_1_" + GSTR1_DataFields.TAXABLE_VALUE.value] or 0)

    def get_tax_difference(self, row_dict):
        row_dict["tax_difference"] = (
            (row_dict["books_" + GSTR1_DataFields.IGST.value] or 0)
            - (row_dict["gstr_1_" + GSTR1_DataFields.IGST.value] or 0)
            + (
                (row_dict["books_" + GSTR1_DataFields.CGST.value] or 0)
                - (row_dict["gstr_1_" + GSTR1_DataFields.CGST.value] or 0)
            )
            + (
                (row_dict["books_" + GSTR1_DataFields.SGST.value] or 0)
                - (row_dict["gstr_1_" + GSTR1_DataFields.SGST.value] or 0)
            )
            + (
                (row_dict["books_" + GSTR1_DataFields.CESS.value] or 0)
                - (row_dict["gstr_1_" + GSTR1_DataFields.CESS.value] or 0)
            )
        )


@frappe.whitelist()
def download_filed_as_excel(company_gstin, month_or_quarter, year):
    frappe.has_permission("GSTR-1 Beta", "export", throw=True)
    GovExcel().generate(company_gstin, get_period(month_or_quarter, year))


@frappe.whitelist()
def download_books_as_excel(company_gstin, month_or_quarter, year):
    frappe.has_permission("GSTR-1 Beta", "export", throw=True)

    books_excel = BooksExcel(company_gstin, month_or_quarter, year)
    books_excel.export_data()


@frappe.whitelist()
def download_reconcile_as_excel(company_gstin, month_or_quarter, year):
    frappe.has_permission("GSTR-1 Beta", "export", throw=True)

    reconcile_excel = ReconcileExcel(company_gstin, month_or_quarter, year)
    reconcile_excel.export_data()


@frappe.whitelist()
def download_gstr_1_json(
    company_gstin,
    year,
    month_or_quarter,
    include_uploaded=False,
    delete_missing=False,
):
    frappe.has_permission("GSTR-1 Beta", "export", throw=True)

    if isinstance(include_uploaded, str):
        include_uploaded = json.loads(include_uploaded)

    if isinstance(delete_missing, str):
        delete_missing = json.loads(delete_missing)

    period = get_period(month_or_quarter, year)
    gstr1_log = frappe.get_doc("GSTR-1 Filed Log", f"{period}-{company_gstin}")

    data = gstr1_log.get_json_for("books")

    for subcategory_data in data.values():
        discard_invoices = []

        if isinstance(subcategory_data, str):
            continue

        for key, row in subcategory_data.items():
            if isinstance(row, list):
                row = row[0]

            if not row.get("upload_status"):
                continue

            if row.get("upload_status") == "Uploaded" and not include_uploaded:
                discard_invoices.append(key)

            if row.get("upload_status") == "Missing in Books":
                if delete_missing:
                    row["flag"] = "D"
                else:
                    discard_invoices.append(key)

        for key in discard_invoices:
            subcategory_data.pop(key)

    return {
        "data": {
            "version": "GST3.0.4",
            "gstin": company_gstin,
            "hash": "hash",
            "fp": period,
            **convert_to_gov_data_format(data),
        },
        "filename": f"GSTR-1-gov-{company_gstin}-{period}.json",
    }
