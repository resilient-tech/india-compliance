"""
Export GSTR-1 data to excel or json
"""

import json
from datetime import datetime
from enum import Enum

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.gst_india.doctype.gstr_1_beta.gstr_1_beta import get_period
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import (
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    GovExcelField,
    GovExcelSheetName,
    GovJsonKey,
    GSTR1_DataField,
    GSTR1_ItemField,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_gov_data_format,
    get_category_wise_data,
)


class ExcelWidth(Enum):
    GSTIN = 15
    NAME = 35
    INVOICE_NUMBER = 15
    DATE = 10
    REVERSE_CHARGE = 10
    DIFF_PERCENTAGE = 10
    TAX_RATE = 10
    INVOICE_COUNT = 10
    QUANTITY = 10
    POS = 30
    DESCRIPTION = 35


CATEGORIES_WITH_ITEMS = {
    GovJsonKey.B2B.value,
    GovJsonKey.B2CL.value,
    GovJsonKey.EXP.value,
    GovJsonKey.CDNR.value,
    GovJsonKey.CDNUR.value,
}


class DataProcessor:

    # transform input data to required format
    FIELD_TRANSFORMATIONS = {}

    def process_data(self, input_data):
        """
        Objective:

        1. Flatten the input data to a list of invoices
        2. Format/Transform the data to match the Gov Excel format
        """

        category_wise_data = get_category_wise_data(input_data)
        processed_data = {}

        for category, data in category_wise_data.items():
            if category in CATEGORIES_WITH_ITEMS:
                data = self.flatten_invoice_items_to_rows(data)

            if self.FIELD_TRANSFORMATIONS:
                data = [self.apply_transformations(row) for row in data]

            processed_data[category] = data

        return processed_data

    def apply_transformations(self, row):
        """
        Apply transformations to row fields
        """
        for field, modifier in self.FIELD_TRANSFORMATIONS.items():
            if field in row:
                row[field] = modifier(row[field])

        return row

    def flatten_invoice_items_to_rows(self, invoice_list: list | tuple) -> list:
        """
        input_data: List of invoices with items
        output: List of invoices with item values

        Example:
            input_data = [
                {
                    "key": "value",
                    "items": [{ "taxable_value": "100" }, { "taxable_value": "200" }]
                }
            ]

            output = [
                {"key": "value", "taxable_value": "100"},
                {"key": "value", "taxable_value": "200"}
            ]

        Purpose: Gov Excel format requires each row to have invoice values
        """
        return [
            {**invoice, **item}
            for invoice in invoice_list
            for item in invoice[GSTR1_DataField.ITEMS.value]
        ]

    def generate_row(self, invoice_data: dict, item: dict):
        """
        Returns invoice row with item values
        TODO: Test and remove
        """
        return {
            **invoice_data,
            GSTR1_ItemField.TAX_RATE.value: item.get(GSTR1_ItemField.TAX_RATE.value, 0),
            GSTR1_ItemField.TAXABLE_VALUE.value: item.get(
                GSTR1_ItemField.TAXABLE_VALUE.value, 0
            ),
            GSTR1_ItemField.CESS.value: item.get(GSTR1_ItemField.CESS.value, 0),
        }


class GovExcel(DataProcessor):
    """
    Export GSTR-1 data to excel

    Excel generated as per the format of Returns Offline Tool Version V3.1.8

    Returns Offline Tool download link - https://www.gst.gov.in/download/returns
    """

    AMOUNT_FORMAT = "#,##0.00"
    DATE_FORMAT = "dd-mmm-yy"
    PERCENT_FORMAT = "0.00"

    FIELD_TRANSFORMATIONS = {
        GSTR1_DataField.DIFF_PERCENTAGE.value: lambda value: (
            value * 100 if value != 0 else None
        ),
        GSTR1_DataField.DOC_DATE.value: lambda value: datetime.strptime(
            value, "%Y-%m-%d"
        ),
        GSTR1_DataField.SHIPPING_BILL_DATE.value: lambda value: datetime.strptime(
            value, "%Y-%m-%d"
        ),
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
                "label": _(GovExcelField.CUST_GSTIN.value),
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "label": _(GovExcelField.CUST_NAME.value),
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": _(GovExcelField.INVOICE_NUMBER.value),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _(GovExcelField.INVOICE_DATE.value),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.INVOICE_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "fieldname": GSTR1_DataField.REVERSE_CHARGE.value,
                "data_format": {"horizontal": "center"},
                "header_format": {"width": ExcelWidth.REVERSE_CHARGE.value},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.INVOICE_TYPE.value),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _(GovExcelField.ECOMMERCE_GSTIN.value),
                # Ignore value, just keep the column
                "fieldname": f"_{GSTR1_DataField.ECOMMERCE_GSTIN.value}",
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_ItemField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_ItemField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_b2cl_headers(self):
        return [
            {
                "label": _(GovExcelField.INVOICE_NUMBER.value),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _(GovExcelField.INVOICE_DATE.value),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.INVOICE_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_ItemField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_ItemField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.ECOMMERCE_GSTIN.value),
                # Ignore value, just keep the column
                "fieldname": f"_{GSTR1_DataField.ECOMMERCE_GSTIN.value}",
            },
        ]

    def get_b2cs_headers(self):
        return [
            {
                "label": _("Type"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_DataField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_DataField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.ECOMMERCE_GSTIN.value),
                # Ignore value, just keep the column
                "fieldname": f"_{GSTR1_DataField.ECOMMERCE_GSTIN.value}",
            },
        ]

    def get_cdnr_headers(self):
        return [
            {
                "label": _(GovExcelField.CUST_GSTIN.value),
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "header_format": {
                    "width": ExcelWidth.GSTIN.value,
                },
            },
            {
                "label": _(GovExcelField.CUST_NAME.value),
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "header_format": {
                    "width": ExcelWidth.NAME.value,
                },
            },
            {
                "label": _(GovExcelField.NOTE_NO.value),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {
                    "width": ExcelWidth.INVOICE_NUMBER.value,
                },
            },
            {
                "label": _(GovExcelField.NOTE_DATE.value),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.NOTE_TYPE.value),
                "fieldname": GSTR1_DataField.TRANSACTION_TYPE.value,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "fieldname": GSTR1_DataField.REVERSE_CHARGE.value,
                "data_format": {"horizontal": "center"},
                "header_format": {"width": ExcelWidth.REVERSE_CHARGE.value},
            },
            {
                "label": _("Note Supply Type"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _(GovExcelField.NOTE_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {
                    "number_format": self.AMOUNT_FORMAT,
                },
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_ItemField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_ItemField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_cdnur_headers(self):
        return [
            {
                "label": _("UR Type"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _(GovExcelField.NOTE_NO.value),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _(GovExcelField.NOTE_DATE.value),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.NOTE_TYPE.value),
                "fieldname": GSTR1_DataField.TRANSACTION_TYPE.value,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _(GovExcelField.NOTE_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_ItemField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_ItemField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_exp_headers(self):
        return [
            {
                "label": _("Export Type"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _(GovExcelField.INVOICE_NUMBER.value),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _(GovExcelField.INVOICE_DATE.value),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.INVOICE_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.PORT_CODE.value),
                "fieldname": GSTR1_DataField.SHIPPING_PORT_CODE.value,
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_NO.value),
                "fieldname": GSTR1_DataField.SHIPPING_BILL_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_DATE.value),
                "fieldname": GSTR1_DataField.SHIPPING_BILL_DATE.value,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_ItemField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_ItemField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_at_headers(self):
        return [
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {
                    "number_format": self.PERCENT_FORMAT,
                },
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _("Gross Advance Received"),
                "fieldname": GSTR1_DataField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_DataField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_txpd_headers(self):
        return [
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": GSTR1_DataField.DIFF_PERCENTAGE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.DIFF_PERCENTAGE.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _("Gross Advance Adjusted"),
                "fieldname": GSTR1_DataField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_DataField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_nil_headers(self):
        return [
            {
                "label": _(GovExcelField.DESCRIPTION.value),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _("Nil Rated Supplies"),
                "fieldname": GSTR1_DataField.NIL_RATED_AMOUNT.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Exempted(other than nil rated/non GST supply)"),
                "fieldname": GSTR1_DataField.EXEMPTED_AMOUNT.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Non-GST Supplies"),
                "fieldname": GSTR1_DataField.NON_GST_AMOUNT.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": _(GovExcelField.HSN_CODE.value),
                "fieldname": GSTR1_DataField.HSN_CODE.value,
            },
            {
                "label": _(GovExcelField.DESCRIPTION.value),
                "fieldname": GSTR1_DataField.DESCRIPTION.value,
            },
            {
                "label": _(GovExcelField.UOM.value),
                "fieldname": GSTR1_DataField.UOM.value,
            },
            {
                "label": _(GovExcelField.QUANTITY.value),
                "fieldname": GSTR1_DataField.QUANTITY.value,
                "header_format": {"width": ExcelWidth.QUANTITY.value},
            },
            {
                "label": _(GovExcelField.TOTAL_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": GSTR1_DataField.TAXABLE_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.IGST.value),
                "fieldname": GSTR1_DataField.IGST.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CGST.value),
                "fieldname": GSTR1_DataField.CGST.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.SGST.value),
                "fieldname": GSTR1_DataField.SGST.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": GSTR1_DataField.CESS.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": _("Nature of Document"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _("Sr. No. From"),
                "fieldname": GSTR1_DataField.FROM_SR.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _("Sr. No. To"),
                "fieldname": GSTR1_DataField.TO_SR.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _("Total Number"),
                "fieldname": GSTR1_DataField.TOTAL_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
            {
                "label": _("Cancelled"),
                "fieldname": GSTR1_DataField.CANCELLED_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
        ]


class BooksExcel(DataProcessor):
    AMOUNT_FORMAT = "#,##0.00"
    DATE_FORMAT = "dd-mmm-yy"
    PERCENT_FORMAT = "0.00"
    DEFAULT_DATA_FORMAT = {"height": 15}

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        gstr1_log = frappe.get_doc("GSTR-1 Filed Log", f"{self.period}-{company_gstin}")

        self.data = self.process_data(gstr1_log.load_data("books")["books"])

    def export_data(self):
        excel = ExcelExporter()
        excel.remove_sheet("Sheet")

        excel.create_sheet(
            sheet_name="invoices",
            headers=self.get_document_headers(),
            data=self.get_document_data(),
            default_data_format=self.DEFAULT_DATA_FORMAT,
            add_totals=False,
        )

        self.create_other_sheets(excel)
        excel.export(get_file_name("books", self.company_gstin, self.period))

    def create_other_sheets(self, excel: ExcelExporter):
        for category in ("HSN", "AT", "TXP", "DOC_ISSUE"):
            data = self.data.get(GovJsonKey[category].value)
            if not data:
                continue

            excel.create_sheet(
                sheet_name=GovExcelSheetName[category].value,
                headers=getattr(self, f"get_{category.lower()}_headers")(),
                data=data,
                default_data_format=self.DEFAULT_DATA_FORMAT,
                add_totals=False,
            )

    def get_document_data(self):
        category = [
            GovJsonKey.B2B.value,
            GovJsonKey.EXP.value,
            GovJsonKey.B2CL.value,
            GovJsonKey.CDNR.value,
            GovJsonKey.CDNUR.value,
            GovJsonKey.B2CS.value,
            GovJsonKey.NIL_EXEMPT.value,
        ]

        category_data = []
        for key, values in self.data.items():
            if key not in category:
                continue

            category_data.extend(values)

        return category_data

    def get_document_headers(self):
        return [
            {
                "label": _("Transaction Type"),
                "fieldname": GSTR1_DataField.TRANSACTION_TYPE.value,
            },
            {
                "label": _("Document Date"),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _("Document Number"),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _("Customer GSTIN"),
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "label": _("Customer Name"),
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": _("Document Type"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_NO.value),
                "fieldname": GSTR1_DataField.SHIPPING_BILL_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_DATE.value),
                "fieldname": GSTR1_DataField.SHIPPING_BILL_DATE.value,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _(GovExcelField.PORT_CODE.value),
                "fieldname": GSTR1_DataField.SHIPPING_PORT_CODE.value,
            },
            {
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "fieldname": GSTR1_DataField.REVERSE_CHARGE.value,
                "header_format": {"width": ExcelWidth.REVERSE_CHARGE.value},
            },
            {
                "label": _("Upload Status"),
                "fieldname": GSTR1_DataField.UPLOAD_STATUS.value,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            {
                "label": _("Tax Rate"),
                "fieldname": GSTR1_ItemField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
            },
            {
                "fieldname": GSTR1_ItemField.TAXABLE_VALUE.value,
                "label": _("Taxable Value"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_ItemField.IGST.value,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_ItemField.CGST.value,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_ItemField.SGST.value,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_ItemField.CESS.value,
                "label": _("CESS"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Document Value"),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
            },
        ]

    def get_at_headers(self):
        return [
            {
                "label": _("Advance Date"),
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _("Payment Entry Number"),
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _("Customer"),
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS.value,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            *self.get_amount_headers(),
            {
                "label": _("Amount Received"),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
            },
        ]

    def get_txp_headers(self):
        return [
            {
                "label": _("Adjustment Date"),
                "fieldname": GSTR1_DataField.DOC_DATE,
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "label": _("Adjustment Entry Number"),
                "fieldname": GSTR1_DataField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "label": _("Customer"),
                "fieldname": GSTR1_DataField.CUST_NAME,
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": GSTR1_DataField.POS,
                "header_format": {"width": ExcelWidth.POS.value},
            },
            *self.get_amount_headers(),
            {
                "label": _("Amount Adjusted"),
                "fieldname": GSTR1_DataField.DOC_VALUE,
            },
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": _("HSN Code"),
                "fieldname": GSTR1_DataField.HSN_CODE.value,
            },
            {
                "label": _(GovExcelField.DESCRIPTION.value),
                "fieldname": GSTR1_DataField.DESCRIPTION.value,
                "header_format": {"width": ExcelWidth.DESCRIPTION.value},
            },
            {
                "label": _("UOM"),
                "fieldname": GSTR1_DataField.UOM.value,
            },
            {
                "label": _(GovExcelField.QUANTITY.value),
                "fieldname": GSTR1_DataField.QUANTITY.value,
                "header_format": {"width": ExcelWidth.QUANTITY.value},
            },
            {
                "label": _(GovExcelField.TOTAL_VALUE.value),
                "fieldname": GSTR1_DataField.DOC_VALUE.value,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            *self.get_amount_headers(),
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": _("Document Type"),
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
            },
            {
                "label": _("Sr No From"),
                "fieldname": GSTR1_DataField.FROM_SR.value,
            },
            {
                "label": _("Sr No To"),
                "fieldname": GSTR1_DataField.TO_SR.value,
            },
            {
                "label": _("Total Count"),
                "fieldname": GSTR1_DataField.TOTAL_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
            {
                "label": _("Draft Count"),
                "fieldname": GSTR1_DataField.DRAFT_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
            {
                "label": _("Cancelled Count"),
                "fieldname": GSTR1_DataField.CANCELLED_COUNT.value,
                "header_format": {"width": ExcelWidth.INVOICE_COUNT.value},
            },
        ]

    def get_amount_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.TAXABLE_VALUE.value,
                "label": _("Taxable Value"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.IGST.value,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.CGST.value,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.SGST.value,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.CESS.value,
                "label": _("CESS"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]


class ReconcileExcel:
    AMOUNT_FORMAT = "#,##0.00"
    DATE_FORMAT = "dd-mmm-yy"

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

    DEFAULT_HEADER_FORMAT = {"bg_color": COLOR_PALLATE.dark_gray}
    DEFAULT_DATA_FORMAT = {"bg_color": COLOR_PALLATE.light_gray}

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        gstr1_log = frappe.get_doc("GSTR-1 Filed Log", f"{self.period}-{company_gstin}")

        self.summary = gstr1_log.load_data("reconcile_summary")["reconcile_summary"]
        data = gstr1_log.load_data("reconcile")["reconcile"]
        self.data = get_category_wise_data(data)

    def export_data(self):
        excel = ExcelExporter()
        excel.remove_sheet("Sheet")

        excel.create_sheet(
            sheet_name="reconcile summary",
            headers=self.get_reconcile_summary_headers(),
            data=self.get_reconcile_summary_data(),
            default_data_format=self.DEFAULT_DATA_FORMAT,
            default_header_format=self.DEFAULT_HEADER_FORMAT,
            add_totals=False,
        )

        for category in (
            "B2B",
            "EXP",
            "B2CL",
            "B2CS",
            "NIL_EXEMPT",
            "CDNR",
            "CDNUR",
            "AT",
            "TXP",
            "HSN",
            "DOC_ISSUE",
        ):
            self.create_sheet(excel, category)

        excel.export(get_file_name("reconcile", self.company_gstin, self.period))

    def get_reconcile_summary_headers(self):
        headers = [
            {
                "fieldname": GSTR1_DataField.DESCRIPTION.value,
                "label": _(GovExcelField.DESCRIPTION.value),
                "header_format": {"width": ExcelWidth.DESCRIPTION.value},
            },
            {
                "fieldname": GSTR1_DataField.TAXABLE_VALUE.value,
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.IGST.value,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.CGST.value,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.SGST.value,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": GSTR1_DataField.CESS.value,
                "label": _("CESS"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
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

    def create_sheet(self, excel: ExcelExporter, category):
        data = self.get_data(category)
        if not data:
            return

        category_key = GovJsonKey[category].value
        merged_headers = getattr(
            self,
            f"get_merge_headers_for_{category_key}",
            self.get_merge_headers,
        )()

        excel.create_sheet(
            sheet_name=GovExcelSheetName[category].value,
            merged_headers=merged_headers,
            headers=getattr(self, f"get_{category_key}_headers")(),
            data=data,
            default_data_format=self.DEFAULT_DATA_FORMAT,
            default_header_format=self.DEFAULT_HEADER_FORMAT,
            add_totals=False,
        )

    def get_data(self, category):
        data = self.data.get(GovJsonKey[category].value, [])
        excel_data = []

        for row in data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_merge_headers(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataField.POS.value,
                    "books_" + GSTR1_DataField.CESS.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataField.POS.value,
                    "gstr_1_" + GSTR1_DataField.CESS.value,
                ],
            }
        )

    def get_merge_headers_for_doc_issue(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataField.FROM_SR.value,
                    "books_" + GSTR1_DataField.CANCELLED_COUNT.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataField.FROM_SR.value,
                    "gstr_1_" + GSTR1_DataField.CANCELLED_COUNT.value,
                ],
            }
        )

    def get_merge_headers_for_hsn(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + GSTR1_DataField.UOM.value,
                    "books_" + GSTR1_DataField.CESS.value,
                ],
                "GSTR-1": [
                    "gstr_1_" + GSTR1_DataField.UOM.value,
                    "gstr_1_" + GSTR1_DataField.CESS.value,
                ],
            }
        )

    def get_b2b_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_common_compare_columns(),
        ]

    def get_b2cl_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_tax_details_columns(for_books=True),
            *self.get_amount_field_columns(for_books=True, only_igst=True),
            *self.get_tax_details_columns(for_books=False),
            *self.get_amount_field_columns(for_books=False, only_igst=True),
        ]

    def get_exp_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                "fieldname": GSTR1_DataField.SHIPPING_BILL_NUMBER.value,
                "label": _(GovExcelField.SHIPPING_BILL_NO.value),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.SHIPPING_BILL_DATE.value,
                "label": _(GovExcelField.SHIPPING_BILL_DATE.value),
                "header_format": {"width": ExcelWidth.DATE.value},
            },
            {
                "fieldname": GSTR1_DataField.SHIPPING_PORT_CODE.value,
                "label": _("Shipping Port Code"),
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + GSTR1_DataField.POS.value,
                "label": _(GovExcelField.POS.value),
                "compare_with": "gstr_1_" + GSTR1_DataField.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            *self.get_tax_details_columns(for_books=True),
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.POS.value,
                "label": _(GovExcelField.POS.value),
                "compare_with": "books_" + GSTR1_DataField.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            *self.get_amount_field_columns(for_books=False, only_igst=True),
        ]

    def get_b2cs_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {
                # TODO: Check this if it works as common field
                "fieldname": GSTR1_DataField.TAX_RATE.value,
                "label": _("Tax Rate"),
                "header_format": {"width": ExcelWidth.TAX_RATE.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_common_compare_columns(),
        ]

    def get_nil_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            # TODO: Fix this
            *self.get_common_compare_columns(),
        ]

    def get_cdnr_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_common_compare_columns(),
        ]

    def get_cdnur_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_TYPE.value,
                "label": _("Document Type"),
            },
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_GSTIN.value,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.GSTIN.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_common_compare_columns(),
        ]

    def get_doc_issue_headers(self):
        headers = [
            {"fieldname": GSTR1_DataField.DOC_TYPE.value, "label": _("Document Type")},
            {
                "fieldname": "match_status",
                "label": _("Match Status"),
            },
            {
                "fieldname": "books_" + GSTR1_DataField.FROM_SR.value,
                "label": _("SR No From"),
                "compare_with": "gstr_1_" + GSTR1_DataField.FROM_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataField.TO_SR.value,
                "label": _("SR No To"),
                "compare_with": "gstr_1_" + GSTR1_DataField.TO_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataField.TOTAL_COUNT.value,
                "label": _("Total Count"),
                "compare_with": "gstr_1_" + GSTR1_DataField.TOTAL_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataField.CANCELLED_COUNT.value,
                "label": _("Cancelled Count"),
                "compare_with": "gstr_1_" + GSTR1_DataField.CANCELLED_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.FROM_SR.value,
                "label": _("Sr No From"),
                "compare_with": "books_" + GSTR1_DataField.FROM_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.TO_SR.value,
                "label": _("Sr No To"),
                "compare_with": "books_" + GSTR1_DataField.TO_SR.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.TOTAL_COUNT.value,
                "label": _("Total Count"),
                "compare_with": "books_" + GSTR1_DataField.TOTAL_COUNT.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.INVOICE_COUNT.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.CANCELLED_COUNT.value,
                "label": _("Cancelled Count"),
                "compare_with": "books_" + GSTR1_DataField.CANCELLED_COUNT.value,
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

    def get_hsn_headers(self):
        headers = [
            {"fieldname": GSTR1_DataField.HSN_CODE.value, "label": _("HSN Code")},
            {"fieldname": GSTR1_DataField.DESCRIPTION.value, "label": _("Description")},
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + GSTR1_DataField.UOM.value,
                "label": _(GovExcelField.UOM.value),
                "compare_with": "gstr_1_" + GSTR1_DataField.UOM.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataField.QUANTITY.value,
                "label": _("Quantity"),
                "compare_with": "gstr_1_" + GSTR1_DataField.QUANTITY.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.QUANTITY.value,
                },
            },
            {
                "fieldname": "books_" + GSTR1_DataField.TAX_RATE.value,
                "label": _("Tax Rate"),
                "compare_with": "gstr_1_" + GSTR1_DataField.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            *self.get_amount_field_columns(for_books=True),
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.UOM.value,
                "label": _(GovExcelField.UOM.value),
                "compare_with": "books_" + GSTR1_DataField.UOM.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.QUANTITY.value,
                "label": _("Quantity"),
                "compare_with": "books_" + GSTR1_DataField.QUANTITY.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.QUANTITY.value,
                },
            },
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.TAX_RATE.value,
                "label": _("Tax Rate"),
                "compare_with": "books_" + GSTR1_DataField.TAX_RATE.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.TAX_RATE.value,
                },
            },
            *self.get_amount_field_columns(for_books=False),
        ]

        return headers

    def get_at_headers(self):
        return [
            {
                "fieldname": GSTR1_DataField.DOC_DATE.value,
                "label": _("Advance Date"),
                "header_format": {
                    "width": ExcelWidth.DATE.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": GSTR1_DataField.DOC_NUMBER.value,
                "label": _("Payment Entry Number"),
                "header_format": {"width": ExcelWidth.INVOICE_NUMBER.value},
            },
            {
                "fieldname": GSTR1_DataField.CUST_NAME.value,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.NAME.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + GSTR1_DataField.POS.value,
                "label": _("POS"),
                "compare_with": "gstr_1_" + GSTR1_DataField.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.POS.value,
                },
            },
            *self.get_amount_field_columns(for_books=True),
            {
                "fieldname": "gstr_1_" + GSTR1_DataField.POS.value,
                "label": _("POS"),
                "compare_with": "books_" + GSTR1_DataField.POS.value,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.POS.value,
                },
            },
            *self.get_amount_field_columns(for_books=False),
        ]

    def get_txpd_headers(self):
        return self.get_at_headers()

    def get_row_dict(self, row: dict) -> dict:
        books = row.pop("books", {})
        gstr_1 = row.pop("gov", {})

        row.update({"books_" + key: value for key, value in books.items()})
        row.update({"gstr_1_" + key: value for key, value in gstr_1.items()})

        doc_date = row.get(GSTR1_DataField.DOC_DATE.value)
        row[GSTR1_DataField.DOC_DATE.value] = getdate(doc_date) if doc_date else ""

        self.update_differences(row)

        return row

    def update_differences(self, row_dict):
        taxable_value_key = GSTR1_DataField.TAXABLE_VALUE.value
        igst_key = GSTR1_DataField.IGST.value
        cgst_key = GSTR1_DataField.CGST.value
        sgst_key = GSTR1_DataField.SGST.value
        cess_key = GSTR1_DataField.CESS.value

        row_dict["taxable_value_difference"] = (
            row_dict.get("books_" + taxable_value_key, 0)
        ) - (row_dict.get("gstr_1_" + taxable_value_key, 0))

        row_dict["tax_difference"] = 0
        for tax_key in [igst_key, cgst_key, sgst_key, cess_key]:
            row_dict["tax_difference"] += row_dict.get("books_" + tax_key, 0) - (
                row_dict.get("gstr_1_" + tax_key, 0)
            )

    # COMMON COLUMNS

    def get_tax_difference_columns(self):
        return [
            {
                "fieldname": "taxable_value_difference",
                "label": _("Taxable Value Difference"),
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
            {
                "fieldname": "tax_difference",
                "label": _("Tax Difference"),
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": ExcelWidth.POS.value,
                },
            },
        ]

    def get_common_compare_columns(self):
        return [
            *self.get_tax_details_columns(for_books=True),
            *self.get_amount_field_columns(for_books=True),
            *self.get_tax_details_columns(for_books=False),
            *self.get_amount_field_columns(for_books=False),
        ]

    def get_amount_field_columns(self, for_books=True, only_igst=False):
        if for_books:
            field_prefix = "books_"
            compare_with = "gstr_1_"
            data_format = {
                "bg_color": self.COLOR_PALLATE.light_green,
                "number_format": self.AMOUNT_FORMAT,
            }
            header_format = {"bg_color": self.COLOR_PALLATE.green}

        else:
            field_prefix = "gstr_1_"
            compare_with = "books_"
            data_format = {
                "bg_color": self.COLOR_PALLATE.light_blue,
                "number_format": self.AMOUNT_FORMAT,
            }
            header_format = {"bg_color": self.COLOR_PALLATE.sky_blue}

        def get_cgst_sgst_columns():
            if only_igst:
                return []

            return [
                {
                    "fieldname": field_prefix + GSTR1_DataField.CGST.value,
                    "label": _("CGST"),
                    "compare_with": compare_with + GSTR1_DataField.CGST.value,
                    "data_format": data_format,
                    "header_format": header_format,
                },
                {
                    "fieldname": field_prefix + GSTR1_DataField.SGST.value,
                    "label": _("SGST"),
                    "compare_with": compare_with + GSTR1_DataField.SGST.value,
                    "data_format": data_format,
                    "header_format": header_format,
                },
            ]

        return [
            {
                "fieldname": field_prefix + GSTR1_DataField.TAXABLE_VALUE.value,
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "compare_with": compare_with + GSTR1_DataField.TAXABLE_VALUE.value,
                "data_format": data_format,
                "header_format": header_format,
            },
            {
                "fieldname": field_prefix + GSTR1_DataField.IGST.value,
                "label": _("IGST"),
                "compare_with": compare_with + GSTR1_DataField.IGST.value,
                "data_format": data_format,
                "header_format": header_format,
            },
            *get_cgst_sgst_columns(),
            {
                "fieldname": field_prefix + GSTR1_DataField.CESS.value,
                "label": _("CESS"),
                "compare_with": compare_with + GSTR1_DataField.CESS.value,
                "data_format": data_format,
                "header_format": header_format,
            },
        ]

    def get_tax_details_columns(self, for_books=True):
        if for_books:
            field_prefix = "books_"
            compare_with = "gstr_1_"
            data_color = self.COLOR_PALLATE.light_green
            header_color = self.COLOR_PALLATE.green

        else:
            field_prefix = "gstr_1_"
            compare_with = "books_"
            data_color = self.COLOR_PALLATE.light_blue
            header_color = self.COLOR_PALLATE.sky_blue

        return [
            {
                "fieldname": field_prefix + GSTR1_DataField.POS.value,
                "label": _(GovExcelField.POS.value),
                "compare_with": compare_with + GSTR1_DataField.POS.value,
                "data_format": {"bg_color": data_color},
                "header_format": {"bg_color": header_color},
            },
            {
                "fieldname": field_prefix + GSTR1_DataField.REVERSE_CHARGE.value,
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "compare_with": compare_with + GSTR1_DataField.REVERSE_CHARGE.value,
                "data_format": {"bg_color": data_color},
                "header_format": {
                    "bg_color": header_color,
                    "width": ExcelWidth.REVERSE_CHARGE.value,
                },
            },
        ]


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
            "gstin": company_gstin,
            "fp": period,
            **convert_to_gov_data_format(data),
        },
        "filename": f"GSTR-1-gov-{company_gstin}-{period}.json",
    }


def get_file_name(field_name, gstin, period):
    return f"GSTR-1-{field_name}-{gstin}-{period}"
