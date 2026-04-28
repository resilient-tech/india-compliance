# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import calendar
import json
import os
from collections import defaultdict
from typing import ClassVar

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_first_day, get_last_day
from openpyxl.cell.cell import MergedCell

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.report.gst_purchase_register.gst_purchase_register import (
    AMOUNT_FIELDS_MAP,
)
from india_compliance.gst_india.utils import (
    get_data_file_path,
    get_period,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import (
    GSTR3BInvoices,
)
from india_compliance.gst_india.utils.gstr3b.gstr3b_outward_data import (
    GSTR1_FIELD_MAP,
    INTER_STATE_SECTION_MAP,
    OUTWARD_INTER_STATE_FIELD,
    OUTWARD_SECTION_TAX_FIELDS,
    GSTR3BOutwardInvoices,
)

PURCHASE_INVOICE_DOCTYPES = frozenset(["Purchase Invoice", "Bill of Entry", "Journal Entry"])

# Maps each ITC JSON section to its ty → (sub_category, net_sign) entries.
# net_sign: 1 = add to net ITC, -1 = subtract, 0 = no effect.
ITC_SECTION_MAP = {
    "itc_avl": {
        "IMPG": ("Import Of Goods", 1),
        "IMPS": ("Import Of Service", 1),
        "ISRC": ("ITC on Reverse Charge", 1),
        "ISD": ("Input Service Distributor", 1),
        "OTH": ("All Other ITC", 1),
    },
    "itc_rev": {
        "RUL": ("As per rules 42 & 43 of CGST Rules and section 17(5)", -1),
        "OTH": ("Others", -1),
    },
    "itc_inelg": {
        "RUL": ("Reclaim of ITC Reversal", 0),
        "OTH": ("ITC restricted due to PoS rules", 0),
    },
}

# Maps ty value → sub_category for inward nil/exempt (isup_details).
INWARD_NIL_EXEMPT_MAP = {
    "GST": "Composition Scheme, Exempted, Nil Rated",
    "NONGST": "Non-GST",
}

# Maps GSTR-3B JSON amount keys to the invoice field names used in the summary
ITC_AMOUNT_KEYS = {
    "iamt": "igst_amount",
    "camt": "cgst_amount",
    "samt": "sgst_amount",
    "csamt": "cess_amount",
}


class GSTR3BReport(Document):
    @property
    def filing_status(self):
        status = "Not Filed"
        if not (self.company_gstin and self.month_or_quarter and self.year):
            return status

        period = get_period(self.month_or_quarter, self.year)
        filters = {
            "gstin": self.company_gstin,
            "return_period": period,
            "return_type": "GSTR3B",
        }
        status = frappe.db.get_value("GST Return Log", filters, "filing_status")

        return status or "Not Filed"

    def validate(self):
        self.json_output = ""
        self.generation_status = "In Process"
        if not self.company_gstin:
            frappe.throw(_("Please enter GSTIN for Company {0}").format(self.company))

        if self.enqueue_report:
            frappe.msgprint(_("Initiated report generation in background"), alert=True)
            frappe.enqueue_doc("GSTR 3B Report", self.name, "get_data", queue="long")
            return

        self.get_data()

    def get_data(self):
        try:
            self.report_dict = json.loads(get_json("gstr_3b_report_template"))
            self.report_dict["gstin"] = self.company_gstin
            self.report_dict["ret_period"] = get_period(self.month_or_quarter, self.year)
            self.month_or_quarter_no = get_period(self.month_or_quarter)
            self.from_date = get_first_day(f"{cint(self.year)}-{self.month_or_quarter_no[0]}-01")
            self.to_date = get_last_day(f"{cint(self.year)}-{self.month_or_quarter_no[1]}-01")

            self._process_outward_itc()
            self._process_inward_itc()

            self.report_dict = format_values(self.report_dict)
            self.json_output = frappe.as_json(self.report_dict)
            self.generation_status = "Generated"

            if self.enqueue_report:
                self.db_set(
                    {
                        "json_output": self.json_output,
                        "generation_status": self.generation_status,
                    }
                )

        except Exception as e:
            self.generation_status = "Failed"
            self.db_set({"generation_status": self.generation_status})
            frappe.db.commit()  # nosemgrep
            raise e

        finally:
            frappe.publish_realtime("gstr3b_report_generation", doctype=self.doctype, docname=self.name)

    def _get_filters(self):
        return frappe._dict(
            {
                "company": self.company,
                "company_gstin": self.company_gstin,
                "from_date": self.from_date,
                "to_date": self.to_date,
                "filter_by": self.filter_by,
            }
        )

    def _process_outward_itc(self):
        """
        Tables 3.1 (outward supplies), 3.1.1 (e-commerce), 3.2 (inter-state),
        and 3.3 (advances) — all derived from Sales Invoice data.
        """
        builder = GSTR3BOutwardInvoices(self._get_filters())
        data = builder.get_data()
        self.update_outward_json(data)

    def update_outward_json(self, data):
        """Accumulate classified outward rows into report_dict sections."""
        inter_state_supply = {}

        for invoice in data:
            category = invoice.get("invoice_category")
            section = invoice.get("outward_section")

            if not category or not section:
                continue

            taxable_value = invoice.taxable_value or 0

            target = self.report_dict[category][section]
            target["txval"] += taxable_value

            tax_fields = OUTWARD_SECTION_TAX_FIELDS.get(section)
            if tax_fields:
                for key in tax_fields:
                    target[key] += invoice.get(GSTR1_FIELD_MAP[key]) or 0

            if section == "osup_det":
                self._accumulate_inter_state(invoice, inter_state_supply)

        for (gst_category, _pos), supply_data in inter_state_supply.items():
            inter_sup_section = INTER_STATE_SECTION_MAP.get(gst_category)
            if inter_sup_section:
                self.report_dict["inter_sup"][inter_sup_section].append(supply_data)

    def _accumulate_inter_state(self, invoice, inter_state_supply):
        """Collect inter-state supply data for section 3.2."""
        if not invoice.get(OUTWARD_INTER_STATE_FIELD):
            return

        igst_amount = invoice.igst_amount or 0
        if not igst_amount:
            return

        place_of_supply = invoice.place_of_supply or ""
        key = (invoice.gst_category, place_of_supply)

        if key not in inter_state_supply:
            inter_state_supply[key] = {
                "txval": 0.0,
                "pos": place_of_supply.split("-")[0],
                "iamt": 0.0,
            }

        inter_state_supply[key]["txval"] += invoice.taxable_value or 0
        inter_state_supply[key]["iamt"] += igst_amount

    def _process_inward_itc(self):
        """
        Tables 4 (ITC) and 5 (nil/exempt inward)
        — derived from Purchase Invoice, Bill of Entry, and Journal Entry.
        """
        data = self.get_purchase_data()

        summary = self._get_sub_section_wise_summary(data)

        self._update_eligible_itc_section(summary)
        self._update_inward_nil_exempt_section(summary)

    def get_purchase_data(self):
        gstr3b = GSTR3BInvoices(self._get_filters())
        data = []
        for doctype in PURCHASE_INVOICE_DOCTYPES:
            data.extend(gstr3b.get_data(doctype, group_by_invoice=True))

        return data

    def _get_sub_section_wise_summary(self, data):
        """Return {invoice_sub_category: {amount_field: total}} for all inward data."""
        amount_fields = ["taxable_value"]
        for section_fields in AMOUNT_FIELDS_MAP.values():
            amount_fields.extend(section_fields)

        summary = {}
        for row in data:
            cat = row.get("invoice_sub_category")
            if cat not in summary:
                summary[cat] = {f: 0 for f in amount_fields}

            for field in amount_fields:
                summary[cat][field] += row.get(field) or 0

        return summary

    def _update_eligible_itc_section(self, summary):
        """
        Populate table 4 — ITC eligible (4A), reversed (4B), net (4C) and
        ineligible (4D) — from the sub-category summary.
        """
        itc_elg = self.report_dict["itc_elg"]
        net_itc = itc_elg["itc_net"]

        for section_key, ty_map in ITC_SECTION_MAP.items():
            for entry in itc_elg[section_key]:
                sub_category, net_sign = ty_map[entry["ty"]]
                amounts = summary.get(sub_category)
                if not amounts:
                    continue

                for json_key, field in ITC_AMOUNT_KEYS.items():
                    amount = amounts.get(field) or 0
                    entry[json_key] += amount
                    net_itc[json_key] += amount * net_sign

    def _update_inward_nil_exempt_section(self, summary):
        """Populate table 5 — inward nil/exempt (GST) and non-GST supplies."""
        for entry in self.report_dict["inward_sup"]["isup_details"]:
            sub_category = INWARD_NIL_EXEMPT_MAP[entry["ty"]]
            amounts = summary.get(sub_category)
            if not amounts:
                continue

            entry["inter"] += amounts.get("inter") or 0
            entry["intra"] += amounts.get("intra") or 0


def get_json(template):
    file_path = os.path.join(os.path.dirname(__file__), f"{template}.json")
    with open(file_path) as f:  # nosemgrep
        return cstr(f.read())


def format_values(data, precision=2):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (int, float)):
                data[key] = flt(value, precision)
            elif isinstance(value, dict) or isinstance(value, list):
                format_values(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (int, float)):
                data[i] = flt(item, precision)
            elif isinstance(item, dict) or isinstance(item, list):
                format_values(item)

    return data


@frappe.whitelist()
def view_report(name: str):
    frappe.has_permission("GSTR 3B Report", throw=True)

    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")
    return json.loads(json_data)


@frappe.whitelist()
def make_json(name: str):
    frappe.has_permission("GSTR 3B Report", throw=True)

    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")
    file_name = "GST3B.json"
    frappe.local.response.filename = file_name
    frappe.local.response.filecontent = json_data
    frappe.local.response.type = "download"


@frappe.whitelist()
def download_gstr3b_as_excel(name: str):
    """Download GSTR 3B report as Excel file"""
    frappe.has_permission("GSTR 3B Report", throw=True)
    json_data = frappe.get_value("GSTR 3B Report", name, "json_output")

    if not json_data:
        frappe.throw(_("Report data not found. Please generate the report."))

    data = json.loads(json_data)
    exporter = GSTR3BExcelExporter(data)
    exporter.generate_excel()


class GSTR3BExcelExporter:
    """
    Export GSTR-3B data to Excel format using the official template.

    This class handles data transformation and mapping from JSON to Excel cells
    following the official GSTR-3B offline utility format.
    """

    TEMPLATE_FILE: ClassVar[str] = get_data_file_path("gstr3b_excel_utility_v5.7.xlsx")
    WORKSHEET_NAME: ClassVar[str] = "GSTR-3B"

    _STATE_CODE_TO_NAME: ClassVar[dict] = {code: state for state, code in STATE_NUMBERS.items()}

    # Row mappings for each section (consistent with JSON keys)
    ROWS: ClassVar[dict] = {
        # Header info
        "gstin": 5,
        "year": 5,
        "month": 6,
        # Section 3.1 - Outward supplies
        "osup_det": 11,
        "osup_zero": 12,
        "osup_nil_exmp": 13,
        "isup_rev": 14,
        "osup_nongst": 15,
        "eco_reg_sup": 23,
        # Section 3.2 - Inter-state
        "inter_state_start": 88,
        # Section 4 - ITC
        "itc_import_goods": 31,
        "itc_import_services": 32,
        "itc_reverse_charge": 33,
        "itc_isd": 34,
        "itc_others": 35,
        "itc_reversed_rules": 37,
        "itc_reversed_others": 38,
        "itc_reclaimed": 41,
        "itc_ineligible": 42,
        # Section 5 - Inward supplies
        "inward_gst": 48,
        "inward_non_gst": 49,
    }

    HEADER_COLUMNS: ClassVar[dict] = {
        "gstin": 3,
        "year": 7,
        "month": 7,
    }

    # Section 3.1 - Tax columns
    TAX_COLUMNS: ClassVar[dict] = {
        "txval": 3,
        "iamt": 4,
        "camt": 5,
        "csamt": 7,
    }

    # Section 4 - ITC columns
    ITC_COLUMNS: ClassVar[dict] = {
        "iamt": 3,
        "camt": 4,
        "csamt": 6,
    }

    # Section 5 - Inward supplies columns
    INWARD_COLUMNS: ClassVar[dict] = {
        "inter": 4,
        "intra": 5,
    }

    # ITC type mappings based on 'ty' field in JSON
    ITC_AVAILABLE_TYPES: ClassVar[dict] = {
        "IMPG": "itc_import_goods",
        "IMPS": "itc_import_services",
        "ISRC": "itc_reverse_charge",
        "ISD": "itc_isd",
        "OTH": "itc_others",
    }

    ITC_REVERSED_TYPES: ClassVar[dict] = {
        "RUL": "itc_reversed_rules",
        "OTH": "itc_reversed_others",
    }

    INWARD_SUPPLY_TYPES: ClassVar[dict] = {
        "GST": "inward_gst",
        "NONGST": "inward_non_gst",
    }

    ITC_INELIGIBLE_TYPES: ClassVar[dict] = {
        "RUL": "itc_reclaimed",
        "OTH": "itc_ineligible",
    }

    COLUMN_SETS: ClassVar[dict] = {
        "tax": ["txval", "iamt", "camt", "csamt"],
        "itc": ["iamt", "camt", "csamt"],
        "import_itc": ["iamt", "csamt"],
        "inward": ["inter", "intra"],
        "zero_rated": ["txval", "iamt", "csamt"],
        "taxable_only": ["txval"],
    }

    def __init__(self, data):
        self.data = data
        self.gstin = data.get("gstin")
        self.worksheet = None
        self.month = None
        self.fiscal_year = None

    def generate_excel(self):
        """Generate and export Excel file"""
        if not os.path.exists(self.TEMPLATE_FILE):
            frappe.throw(_("GSTR 3B Excel template not found"))

        excel = ExcelExporter(file=self.TEMPLATE_FILE)
        self._update_worksheet(excel)

        file_name = self._get_filename()
        excel.export(file_name)

    def _get_filename(self):
        return f"GSTR-3B-{self.gstin}-{self.month}-{self.fiscal_year}"

    def _update_worksheet(self, excel):
        self.worksheet = excel.wb[self.WORKSHEET_NAME]

        self._set_header_info()
        self._set_outward_supplies()
        self._set_ecommerce_supplies()
        self._set_inter_state_supplies()
        self._set_itc_details()
        self._set_inward_supplies()

    def _set_header_info(self):
        """Set header information"""
        period = self.data.get("ret_period", "")
        if not period or len(period) < 6:
            return

        try:
            month_num = int(period[:2])
            calendar_year = int(period[2:6])
        except ValueError:
            return

        self.month = calendar.month_name[month_num]
        self.fiscal_year = self._get_fiscal_year(month_num, calendar_year)

        self._set_cell(self.ROWS["gstin"], self.HEADER_COLUMNS["gstin"], self.gstin)
        self._set_cell(self.ROWS["year"], self.HEADER_COLUMNS["year"], self.fiscal_year)
        self._set_cell(self.ROWS["month"], self.HEADER_COLUMNS["month"], self.month)

    def _get_fiscal_year(self, month_num, calendar_year):
        if month_num >= 4:
            fiscal_year_start = str(calendar_year)
            fiscal_year_end = str(calendar_year + 1)[2:]
        else:
            fiscal_year_start = str(calendar_year - 1)
            fiscal_year_end = str(calendar_year)[2:]

        return f"{fiscal_year_start}-{fiscal_year_end}"

    def _set_outward_supplies(self):
        sup_details = self.data.get("sup_details", {})

        section_mappings = [
            ("osup_det", "tax"),
            ("osup_zero", "zero_rated"),
            ("osup_nil_exmp", "taxable_only"),
            ("isup_rev", "tax"),
            ("osup_nongst", "taxable_only"),
        ]

        for json_key, column_set in section_mappings:
            data = sup_details.get(json_key, {})
            self._set_section_data(json_key, data, column_set)

    def _set_ecommerce_supplies(self):
        eco_dtls = self.data.get("eco_dtls", {})
        self._set_section_data("eco_reg_sup", eco_dtls.get("eco_reg_sup", {}), "taxable_only")

    def _set_inter_state_supplies(self):
        inter_sup = self.data.get("inter_sup", {})
        pos_data = self._group_by_place_of_supply(inter_sup)

        if not pos_data:
            return

        for i, (pos, data) in enumerate(sorted(pos_data.items())):
            row = self.ROWS["inter_state_start"] + i
            self._set_inter_state_row(row, pos, data)

    def _group_by_place_of_supply(self, inter_sup):
        pos_data = {}
        categories = {
            "unreg_details": "unreg",
            "comp_details": "comp",
            "uin_details": "uin",
        }

        for category_key, category_name in categories.items():
            for item in inter_sup.get(category_key, []):
                state_code = item.get("pos", "00")
                state_name = self._format_place_of_supply(state_code)

                if state_name not in pos_data:
                    pos_data[state_name] = {
                        "unreg": {"txval": 0, "iamt": 0},
                        "comp": {"txval": 0, "iamt": 0},
                        "uin": {"txval": 0, "iamt": 0},
                    }

                pos_data[state_name][category_name]["txval"] += flt(item.get("txval", 0), 2)
                pos_data[state_name][category_name]["iamt"] += flt(item.get("iamt", 0), 2)

        return pos_data

    def _set_inter_state_row(self, row, pos, data):
        self._set_cell(row, 2, pos)

        categories = [
            ("unreg", 3, 4),
            ("comp", 5, 6),
            ("uin", 7, 8),
        ]

        for category, val_col, tax_col in categories:
            category_data = data.get(category, {"txval": 0, "iamt": 0})
            self._set_cell(row, val_col, category_data["txval"])
            self._set_cell(row, tax_col, category_data["iamt"])

    def _set_itc_details(self):
        itc_elg = self.data.get("itc_elg", {})
        self._populate_itc_sections(itc_elg.get("itc_avl", []), self.ITC_AVAILABLE_TYPES)
        self._populate_itc_sections(itc_elg.get("itc_rev", []), self.ITC_REVERSED_TYPES)
        self._populate_itc_sections(itc_elg.get("itc_inelg", []), self.ITC_INELIGIBLE_TYPES)

    def _populate_itc_sections(self, itc_entries, type_mapping):
        for itc_entry in itc_entries:
            itc_type = itc_entry.get("ty", "")
            if itc_type not in type_mapping:
                continue

            row_key = type_mapping[itc_type]
            column_set = "import_itc" if itc_type in ["IMPG", "IMPS"] else "itc"
            self._set_section_data(row_key, itc_entry, column_set, self.ITC_COLUMNS)

    def _set_inward_supplies(self):
        inward_sup = self.data.get("inward_sup", {})
        isup_details = inward_sup.get("isup_details", [])

        for supply_data in isup_details:
            supply_type = supply_data.get("ty")
            if supply_type in self.INWARD_SUPPLY_TYPES:
                row_key = self.INWARD_SUPPLY_TYPES[supply_type]
                self._set_section_data(row_key, supply_data, "inward", self.INWARD_COLUMNS)

    def _set_section_data(self, row_key, data, column_set, columns_dict=None):
        row = self.ROWS[row_key]
        columns = self.COLUMN_SETS[column_set]
        mapping = columns_dict or self.TAX_COLUMNS

        for key in columns:
            if key in mapping:
                value = flt(data.get(key, 0), 2)
                self._set_cell(row, mapping[key], value)

    def _set_cell(self, row, column, value):
        cell = self.worksheet.cell(row, column)
        if not isinstance(cell, MergedCell):
            cell.value = value

    @classmethod
    def _format_place_of_supply(cls, state_code):
        formatted_code = state_code.zfill(2)
        state_name = cls._STATE_CODE_TO_NAME.get(formatted_code, "Other Territory")
        return f"{formatted_code}-{state_name}"
