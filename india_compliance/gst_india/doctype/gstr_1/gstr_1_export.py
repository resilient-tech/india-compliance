"""
Export GSTR-1 data to excel or json
"""

from collections import defaultdict
from datetime import datetime
from typing import ClassVar

import frappe
from frappe import _
from frappe.utils import getdate

from india_compliance.gst_india.utils import (
    get_data_file_path,
    get_period,
    validate_gstin_permission,
)
from india_compliance.gst_india.utils.exporter import (
    AMOUNT_FORMAT,
    COLOR_PALLATE,
    DATE_FORMAT,
    PERCENT_FORMAT,
    ExcelExporter,
    ExcelWidth,
)
from india_compliance.gst_india.utils.gstr_1 import (
    HSN_BIFURCATION_FROM,
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    QUARTERLY_KEYS,
    DocField,
    ExcelLabel,
    HSNKey,
    ItemField,
    JsonKey,
    SheetName,
    SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import (
    convert_to_gov_data_format,
    get_category_wise_data,
)
from india_compliance.gst_india.utils.gstr_1.sections._shared import strip_empty

# Used for storing user preferences for GSTR-1 download sections.
GSTR1_SECTIONS_DEFAULT_KEY = "gstr1_download_sections"


CATEGORIES_WITH_ITEMS = {
    JsonKey.B2B.value,
    JsonKey.B2CL.value,
    JsonKey.EXP.value,
    JsonKey.CDNR.value,
    JsonKey.CDNUR.value,
}


def _get_selected_sections(section: str, is_hsn_bifurcated: bool) -> list[str]:
    """
    HSN can be split into `hsn_b2b` / `hsn_b2c`. Every other
    section uses the JsonKey value as-is.
    """
    if section != JsonKey.HSN.value:
        return [section]

    if is_hsn_bifurcated:
        return [HSNKey.HSN_B2B.value, HSNKey.HSN_B2C.value]

    return [HSNKey.HSN.value]


def _get_excel_sheet_names(selected_sections: list[str]) -> list[str]:
    """Template sheet names that belong to `selected_sections` (excluding the `master` reference sheet)."""
    return [
        JSON_CATEGORY_EXCEL_CATEGORY_MAPPING[key]
        for key in selected_sections
        if key in JSON_CATEGORY_EXCEL_CATEGORY_MAPPING
    ]


class DataProcessor:
    # transform input data to required format
    FIELD_TRANSFORMATIONS: ClassVar[dict] = {}

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
        return [{**invoice, **item} for invoice in invoice_list for item in invoice[DocField.ITEMS]]


class GovExcel(DataProcessor):
    """
    Export GSTR-1 data to excel

    Excel generated as per the format of Returns Offline Tool Version V3.1.8

    Returns Offline Tool download link - https://www.gst.gov.in/download/returns
    """

    AMOUNT_FORMAT = AMOUNT_FORMAT
    DATE_FORMAT = DATE_FORMAT
    PERCENT_FORMAT = PERCENT_FORMAT

    FIELD_TRANSFORMATIONS: ClassVar[dict] = {
        DocField.DIFF_PERCENTAGE: lambda value: value * 100 if value != 0 else None,
        DocField.DOC_DATE: lambda value: datetime.strptime(value, "%Y-%m-%d"),
        DocField.SHIPPING_BILL_DATE: lambda value: datetime.strptime(value, "%Y-%m-%d"),
    }

    TEMPLATE_EXCEL_FILE: ClassVar[dict] = {
        "V2.0": get_data_file_path("gstr1_excel_template_v2.0.xlsx"),
        "V2.1": get_data_file_path("gstr1_excel_template_v2.1.xlsx"),
    }

    def generate(self, gstin, period, sections=None):
        """
        Build excel file
        """
        self.gstin = gstin
        self.period = period
        gstr_1_log = frappe.get_doc("GST Return Log", f"GSTR1-{period}-{gstin}")

        month, year = gstr_1_log.return_period[:2], gstr_1_log.return_period[2:]
        filing_from = getdate(f"{year}-{month}-01")

        is_hsn_bifurcated = filing_from >= HSN_BIFURCATION_FROM
        file_version = "V2.1" if is_hsn_bifurcated else "V2.0"
        file = self.TEMPLATE_EXCEL_FILE.get(file_version)

        self.file_field = "filed" if gstr_1_log.filed else "books"
        data = gstr_1_log.load_data(self.file_field)[self.file_field]
        data = self.process_data(data)

        sheet_names = None
        if sections:
            selected = []
            for section in sections:
                selected.extend(_get_selected_sections(section, is_hsn_bifurcated))
            data = _filter_data_by_sections(data, selected)
            sheet_names = _get_excel_sheet_names(selected)

        self.build_excel(
            data,
            file,
            filename=_get_gov_filename(gstin, period, sections),
            sheet_names=sheet_names,
        )

    def process_data(self, data):
        data.update(data.pop("aggregate_data", {}))
        category_wise_data = super().process_data(data)

        for category, category_data in category_wise_data.items():
            # filter missing in books
            category_wise_data[category] = [
                row for row in category_data if row.get("upload_status") != "Missing in Books"
            ]

            if category == JsonKey.DOC_ISSUE.value:
                self.process_doc_issue_data(category_wise_data[category])

            if category not in [
                JsonKey.CDNR.value,
                JsonKey.CDNUR.value,
                JsonKey.TXP.value,
            ]:
                continue

            # convert to positive values
            for doc in category_wise_data.get(category, []):
                if doc.get(DocField.DOC_TYPE) == "D":
                    continue

                doc.update({key: abs(value) for key, value in doc.items() if isinstance(value, int | float)})

        self.process_hsn_data(category_wise_data)

        return category_wise_data

    def build_excel(self, data, file=None, filename=None, sheet_names=None):
        excel = ExcelExporter(file)

        if excel.has_sheet("Sheet"):
            excel.remove_sheet("Sheet")

        if sheet_names and excel.is_loaded:
            self._filter_selected_section_sheets(excel, sheet_names)

        for category, cat_data in data.items():
            sheet_name = JSON_CATEGORY_EXCEL_CATEGORY_MAPPING.get(category)

            if excel.is_loaded and excel.has_sheet(sheet_name):
                excel.insert_data(
                    sheet_name=sheet_name,
                    headers=self.get_category_headers(category),
                    data=cat_data,
                    start_row=5,
                )

            else:
                excel.create_sheet(
                    sheet_name=sheet_name or category,
                    headers=self.get_category_headers(category),
                    data=cat_data,
                    add_totals=False,
                    default_data_format={"height": 15},
                )

        excel.export(filename or get_file_name("Gov", self.gstin, self.period))

    def _filter_selected_section_sheets(self, excel, sheet_names):
        """Remove every template sheet not in `sheet_names`. Master is always kept."""
        kept = {SheetName.MASTER.value, *sheet_names}
        for sheet_name in list(excel.wb.sheetnames):
            if sheet_name not in kept:
                excel.remove_sheet(sheet_name)

    def process_doc_issue_data(self, data):
        """
        Add draft count to cancelled count for DOC_ISSUE category
        """
        for doc in data.copy():
            if doc.get(DocField.DOC_TYPE).startswith("Excluded from Report"):
                data.remove(doc)
                continue

            doc[DocField.CANCELLED_COUNT] += doc.get(DocField.DRAFT_COUNT, 0)

    def process_hsn_data(self, category_wise_data):
        hsn_data = category_wise_data.pop(JsonKey.HSN.value, None)
        if not hsn_data:
            return

        MAP = {
            SubCategory.HSN.value: HSNKey.HSN.value,  # backward compatibility
            SubCategory.HSN_B2B.value: HSNKey.HSN_B2B.value,
            SubCategory.HSN_B2C.value: HSNKey.HSN_B2C.value,
        }

        new_data = defaultdict(list)

        for row in hsn_data:
            sub_category = row.get(DocField.DOC_TYPE)
            if sub_category not in MAP:
                continue

            new_data[MAP[sub_category]].append(row)

        category_wise_data.update(new_data)

    def get_category_headers(self, category):
        return getattr(self, f"get_{category.lower()}_headers")()

    def get_b2b_headers(self):
        return [
            {
                "label": _(ExcelLabel.CUST_GSTIN),
                "fieldname": DocField.CUST_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.CUST_NAME),
                "fieldname": DocField.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(ExcelLabel.INVOICE_NUMBER),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.INVOICE_DATE),
                "fieldname": DocField.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x.strftime("%d-%b-%y") if x else None,
            },
            {
                "label": _(ExcelLabel.INVOICE_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _(ExcelLabel.REVERSE_CHARGE),
                "fieldname": DocField.REVERSE_CHARGE,
                "data_format": {"horizontal": "center"},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.INVOICE_TYPE),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _(ExcelLabel.ECOMMERCE_GSTIN),
                # Ignore value, just keep the column
                "fieldname": f"_{DocField.ECOMMERCE_GSTIN}",
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": ItemField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": ItemField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_b2cl_headers(self):
        return [
            {
                "label": _(ExcelLabel.INVOICE_NUMBER),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.INVOICE_DATE),
                "fieldname": DocField.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x.strftime("%d-%b-%y") if x else None,
            },
            {
                "label": _(ExcelLabel.INVOICE_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": ItemField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": ItemField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.ECOMMERCE_GSTIN),
                # Ignore value, just keep the column
                "fieldname": f"_{DocField.ECOMMERCE_GSTIN}",
            },
        ]

    def get_b2cs_headers(self):
        return [
            {
                "label": _("Type"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": DocField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": DocField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.ECOMMERCE_GSTIN),
                # Ignore value, just keep the column
                "fieldname": f"_{DocField.ECOMMERCE_GSTIN}",
            },
        ]

    def get_supeco_headers(self):
        return [
            {
                "label": _("Nature of Supply"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _("GSTIN of E-Commerce Operator"),
                "fieldname": DocField.ECOMMERCE_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("E-Commerce Operator Name"),
                "fieldname": DocField.ECOMMERCE_OPERATOR_NAME,
                "header_format": {"width": ExcelWidth.LG.value},
            },
            {
                "label": _("Net value of supplies"),
                "fieldname": DocField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Integrated tax"),
                "fieldname": DocField.IGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Central tax"),
                "fieldname": DocField.CGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("State/UT tax"),
                "fieldname": DocField.SGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Cess"),
                "fieldname": DocField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_cdnr_headers(self):
        return [
            {
                "label": _(ExcelLabel.CUST_GSTIN),
                "fieldname": DocField.CUST_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.CUST_NAME),
                "fieldname": DocField.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(ExcelLabel.NOTE_NO),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.NOTE_DATE),
                "fieldname": DocField.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x.strftime("%d-%b-%y") if x else None,
            },
            {
                "label": _(ExcelLabel.NOTE_TYPE),
                "fieldname": DocField.TRANSACTION_TYPE,
                "transform": lambda x, *args: x[0],
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _(ExcelLabel.REVERSE_CHARGE),
                "fieldname": DocField.REVERSE_CHARGE,
                "data_format": {"horizontal": "center"},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Note Supply Type"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _(ExcelLabel.NOTE_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": ItemField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": ItemField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_cdnur_headers(self):
        def ignore_if_export(value, row):
            if row.get(DocField.DOC_TYPE) not in ("EXPWP", "EXPWOP"):
                return value

        return [
            {
                "label": _("UR Type"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _(ExcelLabel.NOTE_NO),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.NOTE_DATE),
                "fieldname": DocField.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x.strftime("%d-%b-%y") if x else None,
            },
            {
                "label": _(ExcelLabel.NOTE_TYPE),
                "fieldname": DocField.TRANSACTION_TYPE,
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
                "transform": ignore_if_export,
            },
            {
                "label": _(ExcelLabel.NOTE_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": ItemField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": ItemField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_exp_headers(self):
        return [
            {
                "label": _("Export Type"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _(ExcelLabel.INVOICE_NUMBER),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.INVOICE_DATE),
                "fieldname": DocField.DOC_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x.strftime("%d-%b-%y") if x else None,
            },
            {
                "label": _(ExcelLabel.INVOICE_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.PORT_CODE),
                "fieldname": DocField.SHIPPING_PORT_CODE,
            },
            {
                "label": _(ExcelLabel.SHIPPING_BILL_NO),
                "fieldname": DocField.SHIPPING_BILL_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.SHIPPING_BILL_DATE),
                "fieldname": DocField.SHIPPING_BILL_DATE,
                "data_format": {"number_format": self.DATE_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x.strftime("%d-%b-%y") if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": ItemField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": ItemField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_at_headers(self):
        return [
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {
                    "number_format": self.PERCENT_FORMAT,
                },
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Gross Advance Received"),
                "fieldname": DocField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": DocField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_txpd_headers(self):
        return [
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _(ExcelLabel.DIFF_PERCENTAGE),
                "fieldname": DocField.DIFF_PERCENTAGE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
                "transform": lambda x, *args: x if x else None,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Gross Advance Adjusted"),
                "fieldname": DocField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": DocField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_nil_headers(self):
        return [
            {
                "label": _(ExcelLabel.DESCRIPTION),
                "fieldname": DocField.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("Nil Rated Supplies"),
                "fieldname": DocField.NIL_RATED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Exempted(other than nil rated/non GST supply)"),
                "fieldname": DocField.EXEMPTED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Non-GST Supplies"),
                "fieldname": DocField.NON_GST_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": _(ExcelLabel.HSN_CODE),
                "fieldname": DocField.HSN_CODE,
            },
            {
                "label": _(ExcelLabel.DESCRIPTION),
                "fieldname": DocField.DESCRIPTION,
            },
            {
                "label": _(ExcelLabel.UOM),
                "fieldname": DocField.UOM,
            },
            {
                "label": _(ExcelLabel.QUANTITY),
                "fieldname": DocField.QUANTITY,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TOTAL_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "fieldname": DocField.TAXABLE_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.IGST),
                "fieldname": DocField.IGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CGST),
                "fieldname": DocField.CGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.SGST),
                "fieldname": DocField.SGST,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _(ExcelLabel.CESS),
                "fieldname": DocField.CESS,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_hsn_b2b_headers(self):
        return self.get_hsn_headers()

    def get_hsn_b2c_headers(self):
        return self.get_hsn_headers()

    def get_doc_issue_headers(self):
        return [
            {
                "label": _("Nature of Document"),
                "fieldname": DocField.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("Sr. No. From"),
                "fieldname": DocField.FROM_SR,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Sr. No. To"),
                "fieldname": DocField.TO_SR,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Total Number"),
                "fieldname": DocField.TOTAL_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Cancelled"),
                "fieldname": DocField.CANCELLED_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
        ]


class BooksExcel(DataProcessor):
    AMOUNT_FORMAT = "#,##0.00"
    DATE_FORMAT = "dd-mmm-yy"
    PERCENT_FORMAT = "0.00"
    DEFAULT_DATA_FORMAT: ClassVar[dict] = {"height": 15}

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        gstr1_log = frappe.get_doc("GST Return Log", f"GSTR1-{self.period}-{company_gstin}")

        self.data = self.process_data(gstr1_log.load_data("books")["books"])

    def process_data(self, data):
        category_wise_data = super().process_data(data)

        DOC_ITEM_FIELD_MAP = {
            DocField.TAXABLE_VALUE: ItemField.TAXABLE_VALUE,
            DocField.IGST: ItemField.IGST,
            DocField.CGST: ItemField.CGST,
            DocField.SGST: ItemField.SGST,
            DocField.CESS: ItemField.CESS,
        }

        for category, category_data in category_wise_data.items():
            # filter missing in books
            category_wise_data[category] = [
                doc for doc in category_data if doc.get("upload_status") != "Missing in Books"
            ]

            # copy doc value to item fields
            if category != JsonKey.B2CS.value:
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
            data = self.data.get(JsonKey[category].value)

            if not data:
                continue

            excel.create_sheet(
                sheet_name=SheetName[category].value,
                headers=getattr(self, f"get_{category.lower()}_headers")(),
                data=data,
                default_data_format=self.DEFAULT_DATA_FORMAT,
                add_totals=False,
            )

    def get_document_data(self):
        taxable_inv_categories = [
            JsonKey.B2B.value,
            JsonKey.EXP.value,
            JsonKey.B2CL.value,
            JsonKey.CDNR.value,
            JsonKey.CDNUR.value,
            JsonKey.B2CS.value,
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
                "fieldname": DocField.TRANSACTION_TYPE,
            },
            {
                "label": _("Document Date"),
                "fieldname": DocField.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Document Number"),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer GSTIN"),
                "fieldname": DocField.CUST_GSTIN,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer Name"),
                "fieldname": DocField.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("Document Type"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": _(ExcelLabel.SHIPPING_BILL_NO),
                "fieldname": DocField.SHIPPING_BILL_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _(ExcelLabel.SHIPPING_BILL_DATE),
                "fieldname": DocField.SHIPPING_BILL_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.PORT_CODE),
                "fieldname": DocField.SHIPPING_PORT_CODE,
            },
            {
                "label": _(ExcelLabel.REVERSE_CHARGE),
                "fieldname": DocField.REVERSE_CHARGE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Upload Status"),
                "fieldname": DocField.UPLOAD_STATUS,
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": _("Tax Rate"),
                "fieldname": ItemField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "fieldname": ItemField.TAXABLE_VALUE,
                "label": _("Taxable Value"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": ItemField.IGST,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": ItemField.CGST,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": ItemField.SGST,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": ItemField.CESS,
                "label": _("CESS"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": _("Document Value"),
                "fieldname": DocField.DOC_VALUE,
            },
        ]

    def get_at_headers(self):
        return [
            {
                "label": _("Advance Date"),
                "fieldname": DocField.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Payment Entry Number"),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer"),
                "fieldname": DocField.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": "Upload Status",
                "fieldname": DocField.UPLOAD_STATUS,
            },
            *self.get_amount_headers(),
        ]

    def get_txp_headers(self):
        return [
            {
                "label": _("Adjustment Date"),
                "fieldname": DocField.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Adjustment Entry Number"),
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": _("Customer"),
                "fieldname": DocField.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _(ExcelLabel.POS),
                "fieldname": DocField.POS,
            },
            {
                "label": "Upload Status",
                "fieldname": DocField.UPLOAD_STATUS,
            },
            *self.get_amount_headers(),
        ]

    def get_hsn_headers(self):
        return [
            {
                "label": _("HSN Code"),
                "fieldname": DocField.HSN_CODE,
            },
            {
                "label": _(ExcelLabel.DESCRIPTION),
                "fieldname": DocField.DESCRIPTION,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": _("UOM"),
                "fieldname": DocField.UOM,
            },
            {
                "label": _(ExcelLabel.TAX_RATE),
                "fieldname": DocField.TAX_RATE,
                "data_format": {"number_format": self.PERCENT_FORMAT},
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Document Type"),
                "fieldname": DocField.DOC_TYPE,
            },
            {
                "label": "Upload Status",
                "fieldname": DocField.UPLOAD_STATUS,
            },
            {
                "label": _(ExcelLabel.QUANTITY),
                "fieldname": DocField.QUANTITY,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _(ExcelLabel.TOTAL_VALUE),
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            *self.get_amount_headers(),
        ]

    def get_doc_issue_headers(self):
        return [
            {
                "label": _("Document Type"),
                "fieldname": DocField.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": "Upload Status",
                "fieldname": DocField.UPLOAD_STATUS,
            },
            {
                "label": _("Sr No From"),
                "fieldname": DocField.FROM_SR,
            },
            {
                "label": _("Sr No To"),
                "fieldname": DocField.TO_SR,
            },
            {
                "label": _("Total Count"),
                "fieldname": DocField.TOTAL_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Draft Count"),
                "fieldname": DocField.DRAFT_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": _("Cancelled Count"),
                "fieldname": DocField.CANCELLED_COUNT,
                "header_format": {"width": ExcelWidth.XS.value},
            },
        ]

    def get_amount_headers(self):
        return [
            {
                "fieldname": DocField.TAXABLE_VALUE,
                "label": _("Taxable Value"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.IGST,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.CGST,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.SGST,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.CESS,
                "label": _("CESS"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]

    def get_nil_exempt_headers(self):
        return [
            {
                "label": "Transaction Type",
                "fieldname": DocField.TRANSACTION_TYPE,
            },
            {
                "label": "Document Date",
                "fieldname": DocField.DOC_DATE,
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "label": "Document Number",
                "fieldname": DocField.DOC_NUMBER,
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "label": "Customer Name",
                "fieldname": DocField.CUST_NAME,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": "Document Type",
                "fieldname": DocField.DOC_TYPE,
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "label": "Upload Status",
                "fieldname": DocField.UPLOAD_STATUS,
            },
            {
                "label": "Nil Rated Supplies",
                "fieldname": DocField.NIL_RATED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": "Exempted Supplies",
                "fieldname": DocField.EXEMPTED_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": "Non-GST Supplies",
                "fieldname": DocField.NON_GST_AMOUNT,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "label": "Document Value",
                "fieldname": DocField.DOC_VALUE,
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
        ]


class ReconcileExcel:
    AMOUNT_FORMAT = AMOUNT_FORMAT
    DATE_FORMAT = DATE_FORMAT

    COLOR_PALLATE = COLOR_PALLATE

    DEFAULT_HEADER_FORMAT: ClassVar[dict] = {"bg_color": COLOR_PALLATE.dark_gray}
    DEFAULT_DATA_FORMAT: ClassVar[dict] = {"bg_color": COLOR_PALLATE.light_gray}

    def __init__(self, company_gstin, month_or_quarter, year):
        self.company_gstin = company_gstin
        self.month_or_quarter = month_or_quarter
        self.year = year

        self.period = get_period(month_or_quarter, year)
        gstr1_log = frappe.get_doc("GST Return Log", f"GSTR1-{self.period}-{company_gstin}")

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
                "fieldname": DocField.DESCRIPTION,
                "label": _(ExcelLabel.DESCRIPTION),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": DocField.TAXABLE_VALUE,
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.IGST,
                "label": _("IGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.CGST,
                "label": _("CGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.SGST,
                "label": _("SGST"),
                "data_format": {"number_format": self.AMOUNT_FORMAT},
            },
            {
                "fieldname": DocField.CESS,
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

        category_key = JsonKey[category].value
        merged_headers = getattr(
            self,
            f"get_merge_headers_for_{category_key}",
            self.get_merge_headers,
        )()

        excel.create_sheet(
            sheet_name=SheetName[category].value,
            merged_headers=merged_headers,
            headers=getattr(self, f"get_{category_key}_headers")(),
            data=data,
            default_data_format=self.DEFAULT_DATA_FORMAT,
            default_header_format=self.DEFAULT_HEADER_FORMAT,
            add_totals=False,
        )

    def get_data(self, category):
        data = self.data.get(JsonKey[category].value, [])
        excel_data = []

        for row in data:
            row_dict = self.get_row_dict(row)
            excel_data.append(row_dict)

        return excel_data

    def get_merge_headers(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + DocField.POS,
                    "books_" + DocField.CESS,
                ],
                "GSTR-1": [
                    "gstr_1_" + DocField.POS,
                    "gstr_1_" + DocField.CESS,
                ],
            }
        )

    def get_merge_headers_for_exp(self):
        return self.get_merge_headers_for_b2cs()

    def get_merge_headers_for_b2cs(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + DocField.TAXABLE_VALUE,
                    "books_" + DocField.CESS,
                ],
                "GSTR-1": [
                    "gstr_1_" + DocField.TAXABLE_VALUE,
                    "gstr_1_" + DocField.CESS,
                ],
            }
        )

    def get_merge_headers_for_nil(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + DocField.NIL_RATED_AMOUNT,
                    "books_" + DocField.TAXABLE_VALUE,
                ],
                "GSTR-1": [
                    "gstr_1_" + DocField.NIL_RATED_AMOUNT,
                    "gstr_1_" + DocField.TAXABLE_VALUE,
                ],
            }
        )

    def get_merge_headers_for_doc_issue(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + DocField.FROM_SR,
                    "books_" + DocField.CANCELLED_COUNT,
                ],
                "GSTR-1": [
                    "gstr_1_" + DocField.FROM_SR,
                    "gstr_1_" + DocField.CANCELLED_COUNT,
                ],
            }
        )

    def get_merge_headers_for_hsn(self):
        return frappe._dict(
            {
                "Books": [
                    "books_" + DocField.QUANTITY,
                    "books_" + DocField.CESS,
                ],
                "GSTR-1": [
                    "gstr_1_" + DocField.QUANTITY,
                    "gstr_1_" + DocField.CESS,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": DocField.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": DocField.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_GSTIN,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_NAME,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": DocField.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": DocField.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + DocField.POS,
                "label": _(ExcelLabel.POS),
                "compare_with": "gstr_1_" + DocField.POS,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            *self.get_amount_field_columns(for_books=True, only_igst=True),
            {
                "fieldname": "gstr_1_" + DocField.POS,
                "label": _(ExcelLabel.POS),
                "compare_with": "books_" + DocField.POS,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": DocField.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": DocField.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": DocField.SHIPPING_BILL_NUMBER,
                "label": _(ExcelLabel.SHIPPING_BILL_NO),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.SHIPPING_BILL_DATE,
                "label": _(ExcelLabel.SHIPPING_BILL_DATE),
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {
                "fieldname": DocField.SHIPPING_PORT_CODE,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": DocField.POS,
                "label": _(ExcelLabel.POS),
            },
            {
                "fieldname": DocField.TAX_RATE,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + DocField.NIL_RATED_AMOUNT,
                "label": _("Nil-Rated Supplies"),
                "compare_with": "gstr_1_" + DocField.NIL_RATED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "books_" + DocField.EXEMPTED_AMOUNT,
                "label": _("Exempted Supplies"),
                "compare_with": "gstr_1_" + DocField.EXEMPTED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "books_" + DocField.NON_GST_AMOUNT,
                "label": _("Non-GST Supplies"),
                "compare_with": "gstr_1_" + DocField.NON_GST_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "books_" + DocField.TAXABLE_VALUE,
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "compare_with": "gstr_1_" + DocField.TAXABLE_VALUE,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.green},
            },
            {
                "fieldname": "gstr_1_" + DocField.NIL_RATED_AMOUNT,
                "label": _("Nil-Rated Supplies"),
                "compare_with": "books_" + DocField.NIL_RATED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
            {
                "fieldname": "gstr_1_" + DocField.EXEMPTED_AMOUNT,
                "label": _("Exempted Supplies"),
                "compare_with": "books_" + DocField.EXEMPTED_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
            {
                "fieldname": "gstr_1_" + DocField.NON_GST_AMOUNT,
                "label": _("Non-GST Supplies"),
                "compare_with": "books_" + DocField.NON_GST_AMOUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                    "number_format": self.AMOUNT_FORMAT,
                },
                "header_format": {"bg_color": self.COLOR_PALLATE.sky_blue},
            },
            {
                "fieldname": "gstr_1_" + DocField.TAXABLE_VALUE,
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "compare_with": "books_" + DocField.TAXABLE_VALUE,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": DocField.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": DocField.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_GSTIN,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_NAME,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
            },
            {
                "fieldname": DocField.DOC_DATE,
                "label": _("Document Date"),
                "header_format": {
                    "width": ExcelWidth.XS.value,
                    "number_format": self.DATE_FORMAT,
                },
            },
            {
                "fieldname": DocField.DOC_NUMBER,
                "label": _("Document No"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_GSTIN,
                "label": _("Customer GSTIN"),
                "header_format": {"width": ExcelWidth.SM.value},
            },
            {
                "fieldname": DocField.CUST_NAME,
                "label": _("Customer Name"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + DocField.POS,
                "label": _(ExcelLabel.POS),
                "compare_with": "gstr_1_" + DocField.POS,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            *self.get_amount_field_columns(for_books=True, only_igst=True),
            {
                "fieldname": "gstr_1_" + DocField.POS,
                "label": _(ExcelLabel.POS),
                "compare_with": "books_" + DocField.POS,
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
                "fieldname": DocField.DOC_TYPE,
                "label": _("Document Type"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": "match_status",
                "label": _("Match Status"),
            },
            {
                "fieldname": "books_" + DocField.FROM_SR,
                "label": _("SR No From"),
                "compare_with": "gstr_1_" + DocField.FROM_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + DocField.TO_SR,
                "label": _("SR No To"),
                "compare_with": "gstr_1_" + DocField.TO_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                },
            },
            {
                "fieldname": "books_" + DocField.TOTAL_COUNT,
                "label": _("Total Count"),
                "compare_with": "gstr_1_" + DocField.TOTAL_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.XS.value,
                },
            },
            {
                "fieldname": "books_" + DocField.CANCELLED_COUNT,
                "label": _("Cancelled Count"),
                "compare_with": "gstr_1_" + DocField.CANCELLED_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": ExcelWidth.XS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + DocField.FROM_SR,
                "label": _("Sr No From"),
                "compare_with": "books_" + DocField.FROM_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + DocField.TO_SR,
                "label": _("Sr No To"),
                "compare_with": "books_" + DocField.TO_SR,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                },
            },
            {
                "fieldname": "gstr_1_" + DocField.TOTAL_COUNT,
                "label": _("Total Count"),
                "compare_with": "books_" + DocField.TOTAL_COUNT,
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": ExcelWidth.XS.value,
                },
            },
            {
                "fieldname": "gstr_1_" + DocField.CANCELLED_COUNT,
                "label": _("Cancelled Count"),
                "compare_with": "books_" + DocField.CANCELLED_COUNT,
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
            {"fieldname": DocField.HSN_CODE, "label": _("HSN Code")},
            {
                "fieldname": DocField.DESCRIPTION,
                "label": _("Description"),
                "header_format": {"width": ExcelWidth.XXL.value},
            },
            {
                "fieldname": DocField.UOM,
                "label": _(ExcelLabel.UOM),
            },
            {
                "fieldname": DocField.TAX_RATE,
                "label": _(ExcelLabel.TAX_RATE),
                "header_format": {"width": ExcelWidth.XS.value},
            },
            {"fieldname": "match_status", "label": _("Match Status")},
            *self.get_tax_difference_columns(),
            {
                "fieldname": "books_" + DocField.QUANTITY,
                "label": _("Quantity"),
                "compare_with": "gstr_1_" + DocField.QUANTITY,
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
                "fieldname": "gstr_1_" + DocField.QUANTITY,
                "label": _("Quantity"),
                "compare_with": "books_" + DocField.QUANTITY,
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
                "fieldname": DocField.POS,
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

        doc_date = row.get(DocField.DOC_DATE)
        row[DocField.DOC_DATE] = getdate(doc_date) if doc_date else ""

        self.update_differences(row)

        return row

    def update_differences(self, row_dict):
        taxable_value_key = DocField.TAXABLE_VALUE
        igst_key = DocField.IGST
        cgst_key = DocField.CGST
        sgst_key = DocField.SGST
        cess_key = DocField.CESS

        row_dict["taxable_value_difference"] = (row_dict.get("books_" + taxable_value_key, 0)) - (
            row_dict.get("gstr_1_" + taxable_value_key, 0)
        )

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
                    "fieldname": field_prefix + DocField.CGST,
                    "label": _("CGST"),
                    "compare_with": compare_with + DocField.CGST,
                    "data_format": data_format,
                    "header_format": header_format,
                },
                {
                    "fieldname": field_prefix + DocField.SGST,
                    "label": _("SGST"),
                    "compare_with": compare_with + DocField.SGST,
                    "data_format": data_format,
                    "header_format": header_format,
                },
            ]

        return [
            {
                "fieldname": field_prefix + DocField.TAXABLE_VALUE,
                "label": _(ExcelLabel.TAXABLE_VALUE),
                "compare_with": compare_with + DocField.TAXABLE_VALUE,
                "data_format": data_format,
                "header_format": header_format,
            },
            {
                "fieldname": field_prefix + DocField.IGST,
                "label": _("IGST"),
                "compare_with": compare_with + DocField.IGST,
                "data_format": data_format,
                "header_format": header_format,
            },
            *get_cgst_sgst_columns(),
            {
                "fieldname": field_prefix + DocField.CESS,
                "label": _("CESS"),
                "compare_with": compare_with + DocField.CESS,
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
                "fieldname": field_prefix + DocField.POS,
                "label": _(ExcelLabel.POS),
                "compare_with": compare_with + DocField.POS,
                "data_format": {"bg_color": data_color},
                "header_format": {"bg_color": header_color},
            },
            {
                "fieldname": field_prefix + DocField.REVERSE_CHARGE,
                "label": _(ExcelLabel.REVERSE_CHARGE),
                "compare_with": compare_with + DocField.REVERSE_CHARGE,
                "data_format": {"bg_color": data_color},
                "header_format": {
                    "bg_color": header_color,
                    "width": ExcelWidth.XS.value,
                },
            },
        ]


def _filter_data_by_sections(data: dict, sections: list[str] | None) -> dict:
    """
    Keep only entries whose keys belong to `sections`.
    """
    if not sections:
        return data

    return {k: v for k, v in data.items() if k in sections}


def _get_gov_filename(company_gstin: str, period: str, sections: list[str] | None = None) -> str:
    name = f"GSTR-1-Gov-{company_gstin}-{period}"
    if not sections:
        return name
    if len(sections) == 1:
        return f"{name}-{sections[0]}"
    return f"{name}-multi-section"


@frappe.whitelist()
def set_section_preference(sections: str | list[str] | None = None):
    """Persist the user's GSTR-1 download section selection as a user default."""
    frappe.has_permission("GSTR-1", "export", throw=True)
    if isinstance(sections, str):
        sections = frappe.parse_json(sections)
    frappe.defaults.set_user_default(GSTR1_SECTIONS_DEFAULT_KEY, frappe.as_json(sections or []))


@frappe.whitelist()
@validate_gstin_permission(doctype="GST Return Log")
def download_filed_as_excel(
    company_gstin: str, month_or_quarter: str, year: str, sections: str | list[str] | None = None
):
    frappe.has_permission("GSTR-1", "export", throw=True)
    if isinstance(sections, str):
        sections = frappe.parse_json(sections) if sections else None
    GovExcel().generate(company_gstin, get_period(month_or_quarter, year), sections=sections)


@frappe.whitelist()
@validate_gstin_permission(doctype="GST Return Log")
def download_books_as_excel(company_gstin: str, month_or_quarter: str, year: str):
    frappe.has_permission("GSTR-1", "export", throw=True)

    books_excel = BooksExcel(company_gstin, month_or_quarter, year)
    books_excel.export_data()


@frappe.whitelist()
@validate_gstin_permission(doctype="GST Return Log")
def download_reconcile_as_excel(company_gstin: str, month_or_quarter: str, year: str):
    frappe.has_permission("GSTR-1", "export", throw=True)

    reconcile_excel = ReconcileExcel(company_gstin, month_or_quarter, year)
    reconcile_excel.export_data()


@frappe.whitelist()
@validate_gstin_permission(doctype="GST Return Log")
def get_gstr_1_json(
    company_gstin: str,
    year: str,
    month_or_quarter: str,
    include_uploaded: bool = False,
    delete_missing: bool = False,
    sections: str | list[str] | None = None,
):
    frappe.has_permission("GSTR-1", "export", throw=True)
    if isinstance(sections, str):
        sections = frappe.parse_json(sections) if sections else None

    settings = frappe.get_cached_doc("GST Settings")
    if not settings.is_gstr1_api_enabled(company_gstin):
        include_uploaded = True
        delete_missing = False

    period = get_period(month_or_quarter, year)
    gstr1_log = frappe.get_doc("GST Return Log", f"GSTR1-{period}-{company_gstin}")

    data = gstr1_log.get_json_for("books")
    data.update(data.pop("aggregate_data", {}))

    for subcategory, subcategory_data in data.items():
        if subcategory in {
            SubCategory.NIL_EXEMPT.value,
            SubCategory.HSN_B2B.value,
            SubCategory.HSN_B2C.value,
            SubCategory.HSN.value,  # Backwards compatibility
            SubCategory.DOC_ISSUE.value,
            *QUARTERLY_KEYS,
            "rounding_difference",
        }:
            continue

        if subcategory == SubCategory.HSN.value:
            for row in subcategory_data.values():
                if row.get(DocField.HSN_CODE):
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

    # the portal rejects blank fields, so they are dropped here rather than while mapping
    gov_data = strip_empty(convert_to_gov_data_format(data, company_gstin))

    if sections:
        gov_data = _filter_data_by_sections(gov_data, sections)

    return {
        "data": {
            "gstin": company_gstin,
            "fp": period,
            **gov_data,
        },
        "filename": f"{_get_gov_filename(company_gstin, period, sections)}.json",
    }


def get_file_name(field_name, gstin, period):
    return f"GSTR-1-{field_name}-{gstin}-{period}"
