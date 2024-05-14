"""
Export GSTR-1 data to excel or json
"""

import frappe

from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import (
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    GSTR1_DataFields,
    GSTR1_Gov_Categories,
    GSTR1_ItemFields,
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
        data = process_data(data)
        self.build_excel(data)

    def build_excel(self, data):
        excel = ExcelExporter()
        for category, cat_data in data.items():
            excel.create_sheet(
                sheet_name=JSON_CATEGORY_EXCEL_CATEGORY_MAPPING.get(category, category),
                headers=self.get_category_headers(category),
                data=cat_data,
                add_totals=False,
            )

        excel.remove_sheet("Sheet")
        excel.export(self.get_file_name())

    def get_file_name(self):
        filename = [
            "GSTR-1",
            self.file_field,
            self.gstin,
            self.period,
        ]

        return "-".join(filename)

    def get_category_headers(self, category):
        return getattr(self, f"get_{category.lower()}_headers")()

    def get_b2b_headers(self):
        return [
            {
                "label": "GSTIN/UIN of Recipient",
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
            },
            {
                "label": "Receiver Name",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
            },
            {
                "label": "Invoice Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
            },
            {
                "label": "Invoice date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
            },
            {
                "label": "Invoice Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
            },
            {
                "label": "Reverse Charge",
                "fieldname": GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {"horizontal": "center"},
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
            },
            {
                "label": "Invoice Type",
                "fieldname": GSTR1_DataFields.DOC_TYPE.value,
            },
            {
                "label": "Taxable Value",
                "fieldname": GSTR1_ItemFields.TAXABLE_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
            },
            {
                "label": "Invoice date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
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
            },
            {
                "label": "Shipping Bill Date",
                "fieldname": GSTR1_DataFields.SHIPPING_BILL_DATE.value,
                "data_format": self.DATE_FORMAT,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
            },
            {
                "label": "Invoice date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
            },
            {
                "label": "Invoice Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
                "data_format": self.AMOUNT_DATA_FORMAT,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
                "fieldname": GSTR1_DataFields.ECOMMERCE_GSTIN.value,
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
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
                "fieldname": GSTR1_DataFields.ECOMMERCE_GSTIN.value,
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

    def get_cdnr_headers(self):
        return [
            {
                "label": "GSTIN/UIN of Recipient",
                "fieldname": GSTR1_DataFields.CUST_GSTIN.value,
            },
            {
                "label": "Receiver Name",
                "fieldname": GSTR1_DataFields.CUST_NAME.value,
            },
            {
                "label": "Note Number",
                "fieldname": GSTR1_DataFields.DOC_NUMBER.value,
            },
            {
                "label": "Note date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
            },
            {
                "label": "Note Type",
                "fieldname": GSTR1_DataFields.TRANSACTION_TYPE.value,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
            },
            {
                "label": "Reverse Charge",
                "fieldname": GSTR1_DataFields.REVERSE_CHARGE.value,
                "data_format": {"horizontal": "center"},
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
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
            },
            {
                "label": "Note date",
                "fieldname": GSTR1_DataFields.DOC_DATE.value,
                "data_format": self.DATE_FORMAT,
            },
            {
                "label": "Note Type",
                "fieldname": GSTR1_DataFields.TRANSACTION_TYPE.value,
            },
            {
                "label": "Place Of Supply",
                "fieldname": GSTR1_DataFields.POS.value,
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
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
            },
            {
                "label": "Applicable % of Tax Rate",
                "fieldname": GSTR1_DataFields.DIFF_PERCENTAGE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
        return self.get_at_headers()

    def get_hsn_headers(self):
        return [
            {
                "label": "Total Quantity",
                "fieldname": GSTR1_DataFields.QUANTITY.value,
            },
            {
                "label": "Total Value",
                "fieldname": GSTR1_DataFields.DOC_VALUE.value,
            },
            {
                "label": "Rate",
                "fieldname": GSTR1_DataFields.TAX_RATE.value,
                "data_format": self.PERCENTAGE_DATA_FORMAT,
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
            },
            {
                "label": "Sr. No. To",
                "fieldname": GSTR1_DataFields.TO_SR.value,
            },
            {
                "label": "Total Number",
                "fieldname": GSTR1_DataFields.TOTAL_COUNT.value,
            },
            {
                "label": "Cancelled",
                "fieldname": GSTR1_DataFields.CANCELLED_COUNT.value,
            },
        ]


CATEGORIES_WITH_ITEMS = {
    GSTR1_Gov_Categories.B2B.value,
    GSTR1_Gov_Categories.B2CL.value,
    GSTR1_Gov_Categories.EXP.value,
    GSTR1_Gov_Categories.CDNR.value,
    GSTR1_Gov_Categories.CDNUR.value,
}


# TODO: API to export GSTR-1 data to excel
@frappe.whitelist()
def export_gstr_1_to_excel(gstin="24AAUPV7468F1ZW", period="042024"):
    GovExcel().generate(gstin, period)


def get_category_wise_data(input_data):
    return {
        category: flatten_to_invoice_list(data)
        for category, data in _get_category_wise_data(input_data).items()
    }


def create_row(invoice_data, item):
    return {
        **invoice_data,
        GSTR1_ItemFields.TAX_RATE.value: item.get(GSTR1_ItemFields.TAX_RATE.value, 0),
        GSTR1_ItemFields.TAXABLE_VALUE.value: item.get(
            GSTR1_ItemFields.TAXABLE_VALUE.value, 0
        ),
        GSTR1_ItemFields.CESS.value: item.get(GSTR1_ItemFields.CESS.value, 0),
    }


def flatten_to_invoice_list(input_data):
    return [document for documents in input_data.values() for document in documents]


def flatten_invoice_items_to_rows(input_data):
    return [
        create_row(invoice, item)
        for invoice in input_data
        for item in invoice[GSTR1_DataFields.ITEMS.value]
    ]


def process_data(input_data):
    category_wise_data = get_category_wise_data(input_data)

    processed_data = {
        category: (
            flatten_invoice_items_to_rows(data)
            if category in CATEGORIES_WITH_ITEMS
            else data
        )
        for category, data in category_wise_data.items()
    }

    return processed_data
