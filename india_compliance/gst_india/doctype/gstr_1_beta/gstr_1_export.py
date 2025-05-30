"""
Export GSTR-1 data to excel or json
"""

import json
from datetime import datetime
from enum import Enum

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.gst_india.utils import get_period
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import (
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    QUARTERLY_KEYS,
    GovExcelField,
    GovExcelSheetName,
    GovJsonKey,
)
from india_compliance.gst_india.utils.gstr_1 import GSTR1_DataField as df
from india_compliance.gst_india.utils.gstr_1 import (
    GSTR1_ItemField,
    GSTR1_SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_gov_data_format,
    get_category_wise_data,
)


class ExcelWidth(Enum):
    XS = 10
    SM = 15
    MD = 20  # Default
    LG = 25
    XL = 30
    XXL = 35


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
            if row.get(field):
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
            for item in invoice[df.ITEMS]
        ]


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
        df.DIFF_PERCENTAGE: lambda value: (value * 100 if value != 0 else None),
        df.DOC_DATE: lambda value: datetime.strptime(value, "%Y-%m-%d"),
        df.SHIPPING_BILL_DATE: lambda value: datetime.strptime(value, "%Y-%m-%d"),
    }

    def generate(self, gstin, period):
        """
        Build excel file
        """
        self.gstin = gstin
        self.period = period
        gstr_1_log = frappe.get_doc("GST Return Log", f"GSTR1-{period}-{gstin}")

        self.file_field = "filed" if gstr_1_log.filed else "books"
        data = gstr_1_log.load_data(self.file_field)[self.file_field]
        data = self.process_data(data)
        self.build_excel(data)

    def process_data(self, data):
        data = data.update(data.pop("aggregate_data", {}))
        category_wise_data = super().process_data(data)

        for category, category_data in category_wise_data.items():
            # filter missing in books
            category_wise_data[category] = [
                row
                for row in category_data
                if row.get("upload_status") != "Missing in Books"
            ]

            if category == GovJsonKey.DOC_ISSUE.value:
                self.process_doc_issue_data(category_wise_data[category])

            if category not in [
                GovJsonKey.CDNR.value,
                GovJsonKey.CDNUR.value,
                GovJsonKey.TXP.value,
            ]:
                continue

            # convert to positive values
            for doc in category_wise_data.get(category, []):
                if doc.get(df.DOC_TYPE) == "D":
                    continue

                doc.update(
                    {
                        key: abs(value)
                        for key, value in doc.items()
                        if isinstance(value, (int, float))
                    }
                )

        return category_wise_data

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
        excel.export(get_file_name("Gov", self.gstin, self.period))

    def process_doc_issue_data(self, data):
        """
        Add draft count to cancelled count for DOC_ISSUE category
        """
        for doc in data.copy():
            if doc.get(df.DOC_TYPE).startswith("Excluded from Report"):
                data.remove(doc)
                continue

            doc[df.CANCELLED_COUNT] += doc.get(df.DRAFT_COUNT, 0)

    def get_category_headers(self, category):
        return getattr(self, f"get_{category.lower()}_headers")()

    def get_b2b_headers(self):
        return [
            {
                "label": _(GovExcelField.CUST_GSTIN.value),
                "fieldname": df.CUST_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.CUST_NAME.value),
                "fieldname": df.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(GovExcelField.INVOICE_NUMBER.value),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.INVOICE_DATE.value),
                "fieldname": df.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.INVOICE_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "fieldname": df.REVERSE_CHARGE,
                "data_format": {"horizontal": "center"},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.INVOICE_TYPE.value),
                "fieldname": df.DOC_TYPE,
            },
            {
                "label": _(GovExcelField.ECOMMERCE_GSTIN.value),
                # Ignore value, just keep the column
                "fieldname": f"_{df.ECOMMERCE_GSTIN}",
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
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
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.INVOICE_DATE.value),
                "fieldname": df.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.INVOICE_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
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
                "fieldname": f"_{df.ECOMMERCE_GSTIN}",
            },
        ]

    def get_b2cs_headers(self):
        return [
            {
                "label": _("Type"),
                "fieldname": df.DOC_TYPE,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": df.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": df.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.ECOMMERCE_GSTIN.value),
                # Ignore value, just keep the column
                "fieldname": f"_{df.ECOMMERCE_GSTIN}",
            },
        ]

    def get_cdnr_headers(self):
        return [
            {
                "label": _(GovExcelField.CUST_GSTIN.value),
                "fieldname": df.CUST_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.CUST_NAME.value),
                "fieldname": df.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(GovExcelField.NOTE_NO.value),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.NOTE_DATE.value),
                "fieldname": df.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.NOTE_TYPE.value),
                "fieldname": df.TRANSACTION_TYPE,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "fieldname": df.REVERSE_CHARGE,
                "data_format": {"horizontal": "center"},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Note Supply Type"),
                "fieldname": df.DOC_TYPE,
            },
            {
                "label": _(GovExcelField.NOTE_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
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
                "fieldname": df.DOC_TYPE,
            },
            {
                "label": _(GovExcelField.NOTE_NO.value),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.NOTE_DATE.value),
                "fieldname": df.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.NOTE_TYPE.value),
                "fieldname": df.TRANSACTION_TYPE,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.NOTE_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
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
                "fieldname": df.DOC_TYPE,
            },
            {
                "label": _(GovExcelField.INVOICE_NUMBER.value),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.INVOICE_DATE.value),
                "fieldname": df.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.INVOICE_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.PORT_CODE.value),
                "fieldname": df.SHIPPING_PORT_CODE,
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_NO.value),
                "fieldname": df.SHIPPING_BILL_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_DATE.value),
                "fieldname": df.SHIPPING_BILL_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
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
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {
                    "number_format": self.PERCENT_FORMAT,
                },
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Gross Advance Received"),
                "fieldname": df.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": df.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_txpd_headers(self):
        return [
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _(GovExcelField.DIFF_PERCENTAGE.value),
                "fieldname": df.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Gross Advance Adjusted"),
                "fieldname": df.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": df.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_nil_headers(self):
        return [
            {
                "label": _(GovExcelField.DESCRIPTION.value),
                "fieldname": df.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("Nil Rated Supplies"),
                "fieldname": df.NIL_RATED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Exempted(other than nil rated/non GST supply)"),
                "fieldname": df.EXEMPTED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Non-GST Supplies"),
                "fieldname": df.NON_GST_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": _(GovExcelField.HSN_CODE.value),
                "fieldname": df.HSN_CODE,
            },
            {
                "label": _(GovExcelField.DESCRIPTION.value),
                "fieldname": df.DESCRIPTION,
            },
            {
                "label": _(GovExcelField.UOM.value),
                "fieldname": df.UOM,
            },
            {
                "label": _(GovExcelField.QUANTITY.value),
                "fieldname": df.QUANTITY,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TOTAL_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "fieldname": df.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.IGST.value),
                "fieldname": df.IGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CGST.value),
                "fieldname": df.CGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.SGST.value),
                "fieldname": df.SGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(GovExcelField.CESS.value),
                "fieldname": df.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": _("Nature of Document"),
                "fieldname": df.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("Sr. No. From"),
                "fieldname": df.FROM_SR,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Sr. No. To"),
                "fieldname": df.TO_SR,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Total Number"),
                "fieldname": df.TOTAL_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Cancelled"),
                "fieldname": df.CANCELLED_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
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
        gstr1_log = frappe.get_doc(
            "GST Return Log", f"GSTR1-{self.period}-{company_gstin}"
        )

        self.data = self.process_data(gstr1_log.load_data("books")["books"])

    def process_data(self, data):
        category_wise_data = super().process_data(data)

        DOC_ITEM_FIELD_MAP = {
            df.TAXABLE_VALUE: GSTR1_ItemField.TAXABLE_VALUE.value,
            df.IGST: GSTR1_ItemField.IGST.value,
            df.CGST: GSTR1_ItemField.CGST.value,
            df.SGST: GSTR1_ItemField.SGST.value,
            df.CESS: GSTR1_ItemField.CESS.value,
        }

        for category, category_data in category_wise_data.items():
            # filter missing in books
            category_wise_data[category] = [
                doc
                for doc in category_data
                if doc.get("upload_status") != "Missing in Books"
            ]

            # copy doc value to item fields
            if category != GovJsonKey.B2CS.value:
                continue

            for doc in category_wise_data[category]:
                for doc_field, item_field in DOC_ITEM_FIELD_MAP.items():
                    doc[item_field] = doc.get(doc_field, 0)

        return category_wise_data

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
        excel.export(get_file_name("Books", self.company_gstin, self.period))

    def create_other_sheets(self, excel: ExcelExporter):
        for category in ("NIL_EXEMPT", "HSN", "AT", "TXP", "DOC_ISSUE"):
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
        taxable_inv_categories = [
            GovJsonKey.B2B.value,
            GovJsonKey.EXP.value,
            GovJsonKey.B2CL.value,
            GovJsonKey.CDNR.value,
            GovJsonKey.CDNUR.value,
            GovJsonKey.B2CS.value,
        ]

        category_data = []
        for key, values in self.data.items():
            if key not in taxable_inv_categories:
                continue

            category_data.extend(values)

        return category_data

    def get_document_headers(self):
        return [
            {
                "label": _("Transaction Type"),
                "fieldname": df.TRANSACTION_TYPE,
            },
            {
                "label": _("Document Date"),
                "fieldname": df.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Document Number"),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer GSTIN"),
                "fieldname": df.CUST_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer Name"),
                "fieldname": df.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("Document Type"),
                "fieldname": df.DOC_TYPE,
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_NO.value),
                "fieldname": df.SHIPPING_BILL_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(GovExcelField.SHIPPING_BILL_DATE.value),
                "fieldname": df.SHIPPING_BILL_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.PORT_CODE.value),
                "fieldname": df.SHIPPING_PORT_CODE,
            },
            {
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "fieldname": df.REVERSE_CHARGE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Upload Status"),
                "fieldname": df.UPLOAD_STATUS,
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": _("Tax Rate"),
                "fieldname": GSTR1_ItemField.TAX_RATE.value,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
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
                "fieldname": df.DOC_VALUE,
            },
        ]

    def get_at_headers(self):
        return [
            {
                "label": _("Advance Date"),
                "fieldname": df.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Payment Entry Number"),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer"),
                "fieldname": df.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": "Upload Status",
                "fieldname": df.UPLOAD_STATUS,
            },
            *self.get_amount_headers(),
        ]

    def get_txp_headers(self):
        return [
            {
                "label": _("Adjustment Date"),
                "fieldname": df.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Adjustment Entry Number"),
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer"),
                "fieldname": df.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(GovExcelField.POS.value),
                "fieldname": df.POS,
            },
            {
                "label": "Upload Status",
                "fieldname": df.UPLOAD_STATUS,
            },
            *self.get_amount_headers(),
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": _("HSN Code"),
                "fieldname": df.HSN_CODE,
            },
            {
                "label": _(GovExcelField.DESCRIPTION.value),
                "fieldname": df.DESCRIPTION,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("UOM"),
                "fieldname": df.UOM,
            },
            {
                "label": _(GovExcelField.TAX_RATE.value),
                "fieldname": df.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": "Upload Status",
                "fieldname": df.UPLOAD_STATUS,
            },
            {
                "label": _(GovExcelField.QUANTITY.value),
                "fieldname": df.QUANTITY,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(GovExcelField.TOTAL_VALUE.value),
                "fieldname": df.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            *self.get_amount_headers(),
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": _("Document Type"),
                "fieldname": df.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": "Upload Status",
                "fieldname": df.UPLOAD_STATUS,
            },
            {
                "label": _("Sr No From"),
                "fieldname": df.FROM_SR,
            },
            {
                "label": _("Sr No To"),
                "fieldname": df.TO_SR,
            },
            {
                "label": _("Total Count"),
                "fieldname": df.TOTAL_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Draft Count"),
                "fieldname": df.DRAFT_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Cancelled Count"),
                "fieldname": df.CANCELLED_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
        ]

    def get_amount_headers(self):
        return [
            {
                "fieldname": df.TAXABLE_VALUE,
                "label": _("Taxable Value"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.IGST,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.CGST,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.SGST,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.CESS,
                "label": _("CESS"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_nil_exempt_headers(self):
        return [
            {
                "label": "Transaction Type",
                "fieldname": df.TRANSACTION_TYPE,
            },
            {
                "label": "Documenrt Date",
                "fieldname": df.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": "Document Number",
                "fieldname": df.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": "Customer Name",
                "fieldname": df.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": "Document Type",
                "fieldname": df.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": "Upload Status",
                "fieldname": df.UPLOAD_STATUS,
            },
            {
                "label": "Nil Rated Supplies",
                "fieldname": df.NIL_RATED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": "Exempted Supplies",
                "fieldname": df.EXEMPTED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": "Non-GST Supplies",
                "fieldname": df.NON_GST_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": "Document Value",
                "fieldname": df.DOC_VALUE,
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
        gstr1_log = frappe.get_doc(
            "GST Return Log", f"GSTR1-{self.period}-{company_gstin}"
        )

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

        excel.export(get_file_name("Reconcile", self.company_gstin, self.period))

    def get_reconcile_summary_headers(self):
        headers = [
            {
                "fieldname": df.DESCRIPTION,
                "label": _(GovExcelField.DESCRIPTION.value),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": df.TAXABLE_VALUE,
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.IGST,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.CGST,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.SGST,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": df.CESS,
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
                    "books_" + df.POS,
                    "books_" + df.CESS,
                ],
                "GSTR-1": [
                    "gstr_1_" + df.POS,
                    "gstr_1_" + df.CESS,
                ],
            }
        )

    def get_merge_headers_for_exp(self):
        return self.get_merge_headers_for_b2cs()

    def get_merge_headers_for_b2cs(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + df.TAXABLE_VALUE,
                    "books_" + df.CESS,
                ],
                "GSTR-1": [
                    "gstr_1_" + df.TAXABLE_VALUE,
                    "gstr_1_" + df.CESS,
                ],
            }
        )

    def get_merge_headers_for_nil(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + df.NIL_RATED_AMOUNT,
                    "books_" + df.TAXABLE_VALUE,
                ],
                "GSTR-1": [
                    "gstr_1_" + df.NIL_RATED_AMOUNT,
                    "gstr_1_" + df.TAXABLE_VALUE,
                ],
            }
        )

    def get_merge_headers_for_doc_issue(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + df.FROM_SR,
                    "books_" + df.CANCELLED_COUNT,
                ],
                "GSTR-1": [
                    "gstr_1_" + df.FROM_SR,
                    "gstr_1_" + df.CANCELLED_COUNT,
                ],
            }
        )

    def get_merge_headers_for_hsn(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + df.QUANTITY,
                    "books_" + df.CESS,
                ],
                "GSTR-1": [
                    "gstr_1_" + df.QUANTITY,
                    "gstr_1_" + df.CESS,
                ],
            }
        )

    def get_merge_headers_for_at(self):
        return self.get_merge_headers_for_b2cs()

    def get_merge_headers_for_txpd(self):
        return self.get_merge_headers_for_b2cs()

    def get_b2b_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": df.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": df.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_GSTIN,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_common_compare_columns(),
        ]

    def get_b2cl_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": df.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": df.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + df.POS,
                "label": _(GovExcelField.POS.value),
                "compare_with": "gstr_1_" + df.POS,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            *self.get_amount_field_columns(for_books=True, only_igst=True),
            {
                "fieldname": "gstr_1_" + df.POS,
                "label": _(GovExcelField.POS.value),
                "compare_with": "books_" + df.POS,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            *self.get_amount_field_columns(for_books=False, only_igst=True),
        ]

    def get_exp_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": df.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": df.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": df.SHIPPING_BILL_NUMBER,
                "label": _(GovExcelField.SHIPPING_BILL_NO.value),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.SHIPPING_BILL_DATE,
                "label": _(GovExcelField.SHIPPING_BILL_DATE.value),
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "fieldname": df.SHIPPING_PORT_CODE,
                "label": _("Shipping Port Code"),
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_amount_field_columns(for_books=True, only_igst=True),
            *self.get_amount_field_columns(for_books=False, only_igst=True),
        ]

    def get_b2cs_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": df.POS,
                "label": _(GovExcelField.POS.value),
            },
            {
                "fieldname": df.TAX_RATE,
                "label": _("Tax Rate"),
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_amount_field_columns(for_books=True),
            *self.get_amount_field_columns(for_books=False),
        ]

    def get_nil_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + df.NIL_RATED_AMOUNT,
                "label": _("Nil-Rated Supplies"),
                "compare_with": "gstr_1_" + df.NIL_RATED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "books_" + df.EXEMPTED_AMOUNT,
                "label": _("Exempted Supplies"),
                "compare_with": "gstr_1_" + df.EXEMPTED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "books_" + df.NON_GST_AMOUNT,
                "label": _("Non-GST Supplies"),
                "compare_with": "gstr_1_" + df.NON_GST_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "books_" + df.TAXABLE_VALUE,
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "compare_with": "gstr_1_" + df.TAXABLE_VALUE,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "gstr_1_" + df.NIL_RATED_AMOUNT,
                "label": _("Nil-Rated Supplies"),
                "compare_with": "books_" + df.NIL_RATED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
            {
                "fieldname": "gstr_1_" + df.EXEMPTED_AMOUNT,
                "label": _("Exempted Supplies"),
                "compare_with": "books_" + df.EXEMPTED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
            {
                "fieldname": "gstr_1_" + df.NON_GST_AMOUNT,
                "label": _("Non-GST Supplies"),
                "compare_with": "books_" + df.NON_GST_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
            {
                "fieldname": "gstr_1_" + df.TAXABLE_VALUE,
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "compare_with": "books_" + df.TAXABLE_VALUE,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
        ]

    def get_cdnr_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": df.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": df.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_GSTIN,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_common_compare_columns(),
        ]

    def get_cdnur_headers(self):
        return [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": df.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": df.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_GSTIN,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": df.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + df.POS,
                "label": _(GovExcelField.POS.value),
                "compare_with": "gstr_1_" + df.POS,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            *self.get_amount_field_columns(for_books=True, only_igst=True),
            {
                "fieldname": "gstr_1_" + df.POS,
                "label": _(GovExcelField.POS.value),
                "compare_with": "books_" + df.POS,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            *self.get_amount_field_columns(for_books=False, only_igst=True),
        ]

    def get_doc_issue_headers(self):
        headers = [
            {
                "fieldname": df.DOC_TYPE,
                "label": _("Document Type"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": "match_status",
                "label": _("Match Status"),
            },
            {
                "fieldname": "books_" + df.FROM_SR,
                "label": _("SR No From"),
                "compare_with": "gstr_1_" + df.FROM_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + df.TO_SR,
                "label": _("SR No To"),
                "compare_with": "gstr_1_" + df.TO_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + df.TOTAL_COUNT,
                "label": _("Total Count"),
                "compare_with": "gstr_1_" + df.TOTAL_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.XS.value,
                },
            },
            {
                "fieldname": "books_" + df.CANCELLED_COUNT,
                "label": _("Cancelled Count"),
                "compare_with": "gstr_1_" + df.CANCELLED_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.XS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + df.FROM_SR,
                "label": _("Sr No From"),
                "compare_with": "books_" + df.FROM_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + df.TO_SR,
                "label": _("Sr No To"),
                "compare_with": "books_" + df.TO_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + df.TOTAL_COUNT,
                "label": _("Total Count"),
                "compare_with": "books_" + df.TOTAL_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.XS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + df.CANCELLED_COUNT,
                "label": _("Cancelled Count"),
                "compare_with": "books_" + df.CANCELLED_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.XS.value,
                },
            },
        ]

        return headers

    def get_hsn_headers(self):
        headers = [
            {"fieldname": df.HSN_CODE, "label": _("HSN Code")},
            {
                "fieldname": df.DESCRIPTION,
                "label": _("Description"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": df.UOM,
                "label": _(GovExcelField.UOM.value),
            },
            {
                "fieldname": df.TAX_RATE,
                "label": _(GovExcelField.TAX_RATE.value),
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + df.QUANTITY,
                "label": _("Quantity"),
                "compare_with": "gstr_1_" + df.QUANTITY,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.XS.value,
                },
            },
            *self.get_amount_field_columns(for_books=True),
            {
                "fieldname": "gstr_1_" + df.QUANTITY,
                "label": _("Quantity"),
                "compare_with": "books_" + df.QUANTITY,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.XS.value,
                },
            },
            *self.get_amount_field_columns(for_books=False),
        ]

        return headers

    def get_at_headers(self):
        return [
            {
                "fieldname": df.POS,
                "label": _("POS"),
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            *self.get_amount_field_columns(for_books=True),
            *self.get_amount_field_columns(for_books=False),
        ]

    def get_txpd_headers(self):
        return self.get_at_headers()

    def get_row_dict(self, row: dict) -> dict:
        books = row.pop("books", {})
        gstr_1 = row.pop("gov", {})

        row.update({"books_" + key: value for key, value in books.items()})
        row.update({"gstr_1_" + key: value for key, value in gstr_1.items()})

        doc_date = row.get(df.DOC_DATE)
        row[df.DOC_DATE] = getdate(doc_date) if doc_date else ""

        self.update_differences(row)

        return row

    def update_differences(self, row_dict):
        taxable_value_key = df.TAXABLE_VALUE
        igst_key = df.IGST
        cgst_key = df.CGST
        sgst_key = df.SGST
        cess_key = df.CESS

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
                    "fieldname": field_prefix + df.CGST,
                    "label": _("CGST"),
                    "compare_with": compare_with + df.CGST,
                    "data_format": data_format,
                    "header_format": header_format,
                },
                {
                    "fieldname": field_prefix + df.SGST,
                    "label": _("SGST"),
                    "compare_with": compare_with + df.SGST,
                    "data_format": data_format,
                    "header_format": header_format,
                },
            ]

        return [
            {
                "fieldname": field_prefix + df.TAXABLE_VALUE,
                "label": _(GovExcelField.TAXABLE_VALUE.value),
                "compare_with": compare_with + df.TAXABLE_VALUE,
                "data_format": data_format,
                "header_format": header_format,
            },
            {
                "fieldname": field_prefix + df.IGST,
                "label": _("IGST"),
                "compare_with": compare_with + df.IGST,
                "data_format": data_format,
                "header_format": header_format,
            },
            *get_cgst_sgst_columns(),
            {
                "fieldname": field_prefix + df.CESS,
                "label": _("CESS"),
                "compare_with": compare_with + df.CESS,
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
                "fieldname": field_prefix + df.POS,
                "label": _(GovExcelField.POS.value),
                "compare_with": compare_with + df.POS,
                "data_format": {"bg_color": data_color},
                "header_format": {"bg_color": header_color},
            },
            {
                "fieldname": field_prefix + df.REVERSE_CHARGE,
                "label": _(GovExcelField.REVERSE_CHARGE.value),
                "compare_with": compare_with + df.REVERSE_CHARGE,
                "data_format": {"bg_color": data_color},
                "header_format": {
                    "bg_color": header_color,
                    "width": ExcelWidth.XS.value,
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
def get_gstr_1_json(
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
    gstr1_log = frappe.get_doc("GST Return Log", f"GSTR1-{period}-{company_gstin}")

    data = gstr1_log.get_json_for("books")
    data = data.update(data.pop("aggregate_data", {}))

    for subcategory, subcategory_data in data.items():
        if subcategory in {
            GSTR1_SubCategory.NIL_EXEMPT.value,
            GSTR1_SubCategory.HSN_B2B.value,
            GSTR1_SubCategory.HSN_B2C.value,
            GSTR1_SubCategory.HSN.value,  # Backwards compatibility
            GSTR1_SubCategory.DOC_ISSUE.value,
            *QUARTERLY_KEYS,
            "rounding_difference",
        }:
            continue

        if subcategory == GSTR1_SubCategory.HSN.value:
            for row in subcategory_data.values():
                if row.get(df.HSN_CODE):
                    continue

                frappe.throw(
                    _(
                        "GST HSN Code is missing in one or more invoices. Please ensure all invoices include the HSN Code, as it is Mandatory for filing GSTR-1."
                    )
                )

            continue

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
                continue

            if row.get("upload_status") == "Missing in Books":
                if delete_missing:
                    row["flag"] = "D"
                else:
                    discard_invoices.append(key)

        for key in discard_invoices:
            subcategory_data.pop(key)

    gstr1_log.normalize_data(data)

    return {
        "data": {
            "gstin": company_gstin,
            "fp": period,
            **convert_to_gov_data_format(data, company_gstin),
        },
        "filename": f"GSTR-1-Gov-{company_gstin}-{period}.json",
    }


def get_file_name(field_name, gstin, period):
    return f"GSTR-1-{field_name}-{gstin}-{period}"
